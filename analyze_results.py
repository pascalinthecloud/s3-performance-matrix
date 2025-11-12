#!/usr/bin/env python3
"""
S3 Warp Performance Analyzer
Parses warp benchmark results and creates visualization charts
"""

import os
import sys
import re
import json
import subprocess
from pathlib import Path
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

def parse_size(size_str):
    """Convert size string (e.g., '4MiB', '256KiB') to bytes"""
    match = re.match(r'(\d+(?:\.\d+)?)(KiB|MiB|GiB|KB|MB|GB)?', size_str)
    if not match:
        return 0
    
    value = float(match.group(1))
    unit = match.group(2) or 'B'
    
    multipliers = {
        'B': 1,
        'KiB': 1024,
        'MiB': 1024**2,
        'GiB': 1024**3,
        'KB': 1000,
        'MB': 1000**2,
        'GB': 1000**3,
    }
    
    return int(value * multipliers.get(unit, 1))

def format_size(bytes_val):
    """Format bytes to human readable"""
    for unit in ['B', 'KiB', 'MiB', 'GiB']:
        if bytes_val < 1024:
            return f"{bytes_val:.0f}{unit}"
        bytes_val /= 1024
    return f"{bytes_val:.0f}TiB"

def format_throughput(mbps):
    """Format throughput"""
    if mbps >= 1000:
        return f"{mbps/1000:.2f} GB/s"
    return f"{mbps:.2f} MB/s"

def decompress_and_parse_warp_output(zst_file):
    """Decompress .csv.zst file and extract summary statistics"""
    try:
        # Decompress using zstd
        result = subprocess.run(
            ['zstd', '-d', '--stdout', str(zst_file)],
            capture_output=True,
            text=True,
            check=True
        )
        
        csv_content = result.stdout
        lines = csv_content.strip().split('\n')
        
        # Parse CSV header and data
        # Warp typically outputs: operation,objects,bytes,duration,throughput_mb/s,ops/s,errors
        # We'll look for summary statistics in the output
        
        data = {
            'throughput_mbps': 0,
            'ops_per_sec': 0,
            'avg_latency_ms': 0,
            'p99_latency_ms': 0,
            'errors': 0,
            'total_ops': 0
        }
        
        for line in lines:
            if not line or line.startswith('#'):
                continue
            
            # Look for summary or aggregated statistics
            parts = line.split(',')
            if len(parts) >= 6:
                try:
                    # Try to extract throughput and ops/s
                    # Format may vary, this is a common pattern
                    if 'PUT' in line.upper() or 'GET' in line.upper():
                        throughput = float(parts[4]) if len(parts) > 4 else 0
                        ops_sec = float(parts[5]) if len(parts) > 5 else 0
                        
                        data['throughput_mbps'] = max(data['throughput_mbps'], throughput)
                        data['ops_per_sec'] = max(data['ops_per_sec'], ops_sec)
                        
                        if len(parts) > 6:
                            errors = int(parts[6])
                            data['errors'] += errors
                except (ValueError, IndexError):
                    continue
        
        return data
        
    except subprocess.CalledProcessError as e:
        print(f"Error decompressing {zst_file}: {e}")
        return None
    except FileNotFoundError:
        print("Error: zstd not found. Please install it: brew install zstd")
        return None

def parse_warp_log(log_file):
    """Parse the warp log file for summary statistics"""
    data = {
        'throughput_mbps': 0,
        'ops_per_sec': 0,
        'avg_latency_ms': 0,
        'p99_latency_ms': 0,
        'errors': 0,
        'total_ops': 0,
        'success': True
    }
    
    try:
        with open(log_file, 'r') as f:
            content = f.read()
            
            # Look for the Report line with average throughput
            # Format: "Report: PUT. Concurrency: X. Ran: Ys"
            # Next line: " * Average: X.XX MiB/s, XX.XX obj/s"
            report_match = re.search(r'Report:.*?\n\s*\*\s*Average:\s+([\d.]+)\s+(MiB/s|KiB/s|GiB/s),\s+([\d.]+)\s+obj/s', content, re.IGNORECASE)
            if report_match:
                val = float(report_match.group(1))
                unit = report_match.group(2)
                ops = float(report_match.group(3))
                
                # Convert to MB/s (MiB/s)
                if 'KiB' in unit or 'KB' in unit:
                    val /= 1024
                elif 'GiB' in unit or 'GB' in unit:
                    val *= 1024
                
                data['throughput_mbps'] = val
                data['ops_per_sec'] = ops
            
            # Look for latency information
            # Format: " * Reqs: Avg: XX.Xms, 50%: XX.Xms, 90%: XX.Xms, 99%: XX.Xms..."
            latency_match = re.search(r'Reqs:\s+Avg:\s+([\d.]+)ms,.*?99%:\s+([\d.]+)ms', content, re.IGNORECASE)
            if latency_match:
                data['avg_latency_ms'] = float(latency_match.group(1))
                data['p99_latency_ms'] = float(latency_match.group(2))
            
            # Look for errors in the final report
            # Format: "Reqs: 1796, Errs:0, Objs:1796"
            error_match = re.search(r'Errs:\s*(\d+)', content)
            if error_match:
                data['errors'] = int(error_match.group(1))
                if data['errors'] > 0:
                    data['success'] = False
            
            # Total operations from Reqs line
            total_match = re.search(r'Reqs:\s*(\d+),\s*Errs:', content)
            if total_match:
                data['total_ops'] = int(total_match.group(1))
                
    except Exception as e:
        print(f"Error parsing {log_file}: {e}")
        data['success'] = False
    
    return data

def collect_results(results_dir):
    """Collect all test results from the directory"""
    results_path = Path(results_dir)
    results = []
    
    # Pattern: put_<SIZE>_c<CONC>.log
    for log_file in sorted(results_path.glob('put_*.log')):
        filename = log_file.stem
        
        # Extract size and concurrency from filename
        match = re.match(r'put_(.+)_c(\d+)', filename)
        if not match:
            continue
        
        size_str = match.group(1)
        concurrency = int(match.group(2))
        size_bytes = parse_size(size_str)
        
        # Parse the log file
        data = parse_warp_log(log_file)
        
        results.append({
            'size_str': size_str,
            'size_bytes': size_bytes,
            'concurrency': concurrency,
            'throughput_mbps': data['throughput_mbps'],
            'ops_per_sec': data['ops_per_sec'],
            'avg_latency_ms': data['avg_latency_ms'],
            'p99_latency_ms': data['p99_latency_ms'],
            'errors': data['errors'],
            'total_ops': data['total_ops'],
            'success': data['success']
        })
    
    return results

def create_charts(results, output_dir):
    """Create visualization charts"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    if not results:
        print("No results to visualize!")
        return
    
    # Group results by size and concurrency
    by_size = defaultdict(list)
    by_concurrency = defaultdict(list)
    
    for r in results:
        by_size[r['size_str']].append(r)
        by_concurrency[r['concurrency']].append(r)
    
    # Sort sizes by bytes
    sorted_sizes = sorted(by_size.keys(), key=lambda x: parse_size(x))
    sorted_concurrencies = sorted(by_concurrency.keys())
    
    # Create comprehensive charts
    create_throughput_heatmap(results, sorted_sizes, sorted_concurrencies, output_path)
    create_throughput_by_size(by_size, sorted_sizes, output_path)
    create_throughput_by_concurrency(by_concurrency, sorted_concurrencies, output_path)
    create_ops_by_size(by_size, sorted_sizes, output_path)
    create_latency_charts(results, sorted_sizes, sorted_concurrencies, output_path)
    create_optimal_config_chart(results, output_path)
    
    print(f"\n✓ Charts saved to: {output_path}")

def create_throughput_heatmap(results, sizes, concurrencies, output_path):
    """Create heatmap showing throughput across all combinations"""
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Create matrix
    matrix = np.zeros((len(sizes), len(concurrencies)))
    
    for r in results:
        size_idx = sizes.index(r['size_str'])
        conc_idx = concurrencies.index(r['concurrency'])
        matrix[size_idx, conc_idx] = r['throughput_mbps']
    
    im = ax.imshow(matrix, aspect='auto', cmap='RdYlGn', interpolation='nearest')
    
    # Labels
    ax.set_xticks(range(len(concurrencies)))
    ax.set_yticks(range(len(sizes)))
    ax.set_xticklabels(concurrencies)
    ax.set_yticklabels(sizes)
    ax.set_xlabel('Concurrency Level', fontsize=12, fontweight='bold')
    ax.set_ylabel('Object Size', fontsize=12, fontweight='bold')
    ax.set_title('S3 Throughput Heatmap (MB/s)', fontsize=14, fontweight='bold')
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Throughput (MB/s)', fontsize=10)
    
    # Add values to cells
    for i in range(len(sizes)):
        for j in range(len(concurrencies)):
            value = matrix[i, j]
            if value > 0:
                text = ax.text(j, i, f'{value:.0f}',
                             ha="center", va="center", color="black", fontsize=8)
    
    plt.tight_layout()
    plt.savefig(output_path / 'throughput_heatmap.png', dpi=150, bbox_inches='tight')
    plt.close()

def create_throughput_by_size(by_size, sizes, output_path):
    """Bar chart: throughput vs object size for different concurrency levels"""
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Get all concurrency levels
    all_conc = set()
    for size_results in by_size.values():
        for r in size_results:
            all_conc.add(r['concurrency'])
    
    conc_levels = sorted(all_conc)
    x = np.arange(len(sizes))
    width = 0.8 / len(conc_levels)
    
    colors = plt.cm.viridis(np.linspace(0, 1, len(conc_levels)))
    
    for idx, conc in enumerate(conc_levels):
        throughputs = []
        for size in sizes:
            size_results = by_size[size]
            conc_result = next((r for r in size_results if r['concurrency'] == conc), None)
            throughputs.append(conc_result['throughput_mbps'] if conc_result else 0)
        
        ax.bar(x + idx * width, throughputs, width, label=f'C={conc}', color=colors[idx])
    
    ax.set_xlabel('Object Size', fontsize=12, fontweight='bold')
    ax.set_ylabel('Throughput (MB/s)', fontsize=12, fontweight='bold')
    ax.set_title('Throughput by Object Size (Different Concurrency Levels)', fontsize=14, fontweight='bold')
    ax.set_xticks(x + width * (len(conc_levels) - 1) / 2)
    ax.set_xticklabels(sizes, rotation=45, ha='right')
    ax.legend(title='Concurrency', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path / 'throughput_by_size.png', dpi=150, bbox_inches='tight')
    plt.close()

def create_throughput_by_concurrency(by_concurrency, concurrencies, output_path):
    """Bar chart: throughput vs concurrency for different object sizes"""
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # Get all sizes
    all_sizes = set()
    for conc_results in by_concurrency.values():
        for r in conc_results:
            all_sizes.add(r['size_str'])
    
    sizes = sorted(all_sizes, key=parse_size)
    x = np.arange(len(concurrencies))
    width = 0.8 / len(sizes)
    
    colors = plt.cm.plasma(np.linspace(0, 1, len(sizes)))
    
    for idx, size in enumerate(sizes):
        throughputs = []
        for conc in concurrencies:
            conc_results = by_concurrency[conc]
            size_result = next((r for r in conc_results if r['size_str'] == size), None)
            throughputs.append(size_result['throughput_mbps'] if size_result else 0)
        
        ax.bar(x + idx * width, throughputs, width, label=size, color=colors[idx])
    
    ax.set_xlabel('Concurrency Level', fontsize=12, fontweight='bold')
    ax.set_ylabel('Throughput (MB/s)', fontsize=12, fontweight='bold')
    ax.set_title('Throughput by Concurrency Level (Different Object Sizes)', fontsize=14, fontweight='bold')
    ax.set_xticks(x + width * (len(sizes) - 1) / 2)
    ax.set_xticklabels(concurrencies)
    ax.legend(title='Object Size', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path / 'throughput_by_concurrency.png', dpi=150, bbox_inches='tight')
    plt.close()

def create_ops_by_size(by_size, sizes, output_path):
    """Bar chart: operations per second"""
    fig, ax = plt.subplots(figsize=(14, 8))
    
    all_conc = set()
    for size_results in by_size.values():
        for r in size_results:
            all_conc.add(r['concurrency'])
    
    conc_levels = sorted(all_conc)
    x = np.arange(len(sizes))
    width = 0.8 / len(conc_levels)
    
    colors = plt.cm.coolwarm(np.linspace(0, 1, len(conc_levels)))
    
    for idx, conc in enumerate(conc_levels):
        ops = []
        for size in sizes:
            size_results = by_size[size]
            conc_result = next((r for r in size_results if r['concurrency'] == conc), None)
            ops.append(conc_result['ops_per_sec'] if conc_result else 0)
        
        ax.bar(x + idx * width, ops, width, label=f'C={conc}', color=colors[idx])
    
    ax.set_xlabel('Object Size', fontsize=12, fontweight='bold')
    ax.set_ylabel('Operations per Second', fontsize=12, fontweight='bold')
    ax.set_title('Operations per Second by Object Size', fontsize=14, fontweight='bold')
    ax.set_xticks(x + width * (len(conc_levels) - 1) / 2)
    ax.set_xticklabels(sizes, rotation=45, ha='right')
    ax.legend(title='Concurrency', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path / 'ops_by_size.png', dpi=150, bbox_inches='tight')
    plt.close()

def create_latency_charts(results, sizes, concurrencies, output_path):
    """Create latency analysis charts"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    # Filter results with valid latency data
    valid_results = [r for r in results if r['avg_latency_ms'] > 0]
    
    if not valid_results:
        return
    
    # Average latency by concurrency
    by_conc = defaultdict(list)
    for r in valid_results:
        by_conc[r['concurrency']].append(r['avg_latency_ms'])
    
    conc_sorted = sorted(by_conc.keys())
    avg_latencies = [np.mean(by_conc[c]) for c in conc_sorted]
    
    ax1.bar(range(len(conc_sorted)), avg_latencies, color='steelblue')
    ax1.set_xlabel('Concurrency Level', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Average Latency (ms)', fontsize=12, fontweight='bold')
    ax1.set_title('Average Latency by Concurrency', fontsize=13, fontweight='bold')
    ax1.set_xticks(range(len(conc_sorted)))
    ax1.set_xticklabels(conc_sorted)
    ax1.grid(axis='y', alpha=0.3)
    
    # P99 latency by concurrency
    p99_results = [r for r in results if r['p99_latency_ms'] > 0]
    if p99_results:
        by_conc_p99 = defaultdict(list)
        for r in p99_results:
            by_conc_p99[r['concurrency']].append(r['p99_latency_ms'])
        
        conc_sorted_p99 = sorted(by_conc_p99.keys())
        p99_latencies = [np.mean(by_conc_p99[c]) for c in conc_sorted_p99]
        
        ax2.bar(range(len(conc_sorted_p99)), p99_latencies, color='coral')
        ax2.set_xlabel('Concurrency Level', fontsize=12, fontweight='bold')
        ax2.set_ylabel('P99 Latency (ms)', fontsize=12, fontweight='bold')
        ax2.set_title('P99 Latency by Concurrency', fontsize=13, fontweight='bold')
        ax2.set_xticks(range(len(conc_sorted_p99)))
        ax2.set_xticklabels(conc_sorted_p99)
        ax2.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path / 'latency_analysis.png', dpi=150, bbox_inches='tight')
    plt.close()

def create_optimal_config_chart(results, output_path):
    """Identify and visualize optimal configurations"""
    if not results:
        return
    
    # Find top 10 configurations by throughput
    top_results = sorted(results, key=lambda x: x['throughput_mbps'], reverse=True)[:10]
    
    fig, ax = plt.subplots(figsize=(12, 8))
    
    labels = [f"{r['size_str']}\nC={r['concurrency']}" for r in top_results]
    throughputs = [r['throughput_mbps'] for r in top_results]
    colors = plt.cm.RdYlGn(np.linspace(0.5, 1, len(top_results)))
    
    bars = ax.barh(range(len(labels)), throughputs, color=colors)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_xlabel('Throughput (MB/s)', fontsize=12, fontweight='bold')
    ax.set_title('Top 10 Best Performing Configurations', fontsize=14, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)
    
    # Add value labels
    for i, (bar, val) in enumerate(zip(bars, throughputs)):
        ax.text(val + max(throughputs) * 0.01, i, f'{val:.1f} MB/s', 
                va='center', fontsize=10, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_path / 'optimal_configurations.png', dpi=150, bbox_inches='tight')
    plt.close()

def generate_summary_report(results, output_path):
    """Generate text summary report"""
    if not results:
        return
    
    report_path = output_path / 'performance_summary.txt'
    
    with open(report_path, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("S3 WARP PERFORMANCE TEST SUMMARY\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"Total tests: {len(results)}\n")
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        f.write(f"Successful: {successful}\n")
        f.write(f"Failed: {failed}\n\n")
        
        # Best overall
        best = max(results, key=lambda x: x['throughput_mbps'])
        f.write("BEST OVERALL CONFIGURATION:\n")
        f.write("-" * 80 + "\n")
        f.write(f"Object Size: {best['size_str']}\n")
        f.write(f"Concurrency: {best['concurrency']}\n")
        f.write(f"Throughput: {best['throughput_mbps']:.2f} MB/s\n")
        f.write(f"Operations/sec: {best['ops_per_sec']:.2f}\n")
        if best['avg_latency_ms'] > 0:
            f.write(f"Avg Latency: {best['avg_latency_ms']:.2f} ms\n")
        f.write("\n")
        
        # Best by object size
        f.write("BEST CONFIGURATION BY OBJECT SIZE:\n")
        f.write("-" * 80 + "\n")
        by_size = defaultdict(list)
        for r in results:
            by_size[r['size_str']].append(r)
        
        for size in sorted(by_size.keys(), key=parse_size):
            best_for_size = max(by_size[size], key=lambda x: x['throughput_mbps'])
            f.write(f"{size:>10s}: C={best_for_size['concurrency']:<6d} "
                   f"→ {best_for_size['throughput_mbps']:>8.2f} MB/s "
                   f"({best_for_size['ops_per_sec']:.0f} ops/s)\n")
        f.write("\n")
        
        # Performance breakdown analysis
        f.write("PERFORMANCE BREAKDOWN ANALYSIS:\n")
        f.write("-" * 80 + "\n")
        
        # Find where performance starts to degrade
        by_concurrency = defaultdict(list)
        for r in results:
            by_concurrency[r['concurrency']].append(r['throughput_mbps'])
        
        conc_avg = {c: np.mean(vals) for c, vals in by_concurrency.items()}
        sorted_conc = sorted(conc_avg.keys())
        
        peak_conc = max(conc_avg, key=conc_avg.get)
        peak_throughput = conc_avg[peak_conc]
        
        f.write(f"Peak average throughput at concurrency: {peak_conc}\n")
        f.write(f"Peak average throughput: {peak_throughput:.2f} MB/s\n\n")
        
        # Identify breakdown point (where throughput drops > 20%)
        breakdown_threshold = 0.8
        for i, conc in enumerate(sorted_conc):
            if i > 0 and conc_avg[conc] < conc_avg[sorted_conc[i-1]] * breakdown_threshold:
                f.write(f"⚠ Performance degradation detected at concurrency: {conc}\n")
                f.write(f"  Throughput dropped to {conc_avg[conc]:.2f} MB/s "
                       f"(from {conc_avg[sorted_conc[i-1]]:.2f} MB/s)\n\n")
                break
        
        f.write("=" * 80 + "\n")
    
    print(f"✓ Summary report saved to: {report_path}")
    
    # Print to console
    with open(report_path, 'r') as f:
        print("\n" + f.read())

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_results.py <results_directory>")
        sys.exit(1)
    
    results_dir = sys.argv[1]
    
    if not os.path.exists(results_dir):
        print(f"Error: Directory not found: {results_dir}")
        sys.exit(1)
    
    print(f"Analyzing results from: {results_dir}")
    print("=" * 80)
    
    # Collect results
    print("\nCollecting test results...")
    results = collect_results(results_dir)
    
    if not results:
        print("No results found! Make sure .log files exist in the directory.")
        sys.exit(1)
    
    print(f"Found {len(results)} test results")
    
    # Create output directory for charts
    charts_dir = Path(results_dir) / 'charts'
    
    # Generate visualizations
    print("\nGenerating charts...")
    create_charts(results, charts_dir)
    
    # Generate summary report
    print("\nGenerating summary report...")
    generate_summary_report(results, charts_dir)
    
    print("\n" + "=" * 80)
    print("Analysis complete!")
    print("=" * 80)

if __name__ == '__main__':
    main()
