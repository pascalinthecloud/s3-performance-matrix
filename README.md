# S3 Warp Performance Testing Suite

This suite helps you identify optimal S3 performance configurations by testing various object sizes and concurrency levels, then visualizing the results.

## Prerequisites

1. **Warp binary**: Download from [github.com/minio/warp](https://github.com/minio/warp/releases)
   ```bash
   # macOS example
   wget https://github.com/minio/warp/releases/latest/download/warp_darwin_amd64 -O warp
   chmod +x warp
   ```

2. **Python 3** with matplotlib and numpy:
   ```bash
   pip3 install matplotlib numpy
   ```

3. **zstd** (for decompressing results):
   ```bash
   brew install zstd
   ```

4. **AWS Credentials**: Set environment variables:
   ```bash
   export AWS_ACCESS_KEY_ID="your-access-key"
   export AWS_SECRET_ACCESS_KEY="your-secret-key"
   ```

## Configuration

Edit `run_warp.sh` to configure:
- `HOST`: Your S3 endpoint
- `BUCKET`: Bucket name for testing
- `DUR`: Test duration per configuration (default: 1m)
- `SIZES`: Array of object sizes to test
- `CONCURRENCIES`: Array of concurrency levels to test

## Running Tests

### Full Test Suite
```bash
./run_warp.sh
```

This will:
- Test all combinations of object sizes (1KiB to 128MiB) and concurrency levels (1 to 2048)
- Save results to a timestamped directory: `results_YYYYMMDD_HHMMSS/`
- Create `.log` files for each test configuration
- Show progress: `[current/total] Testing: Size=4MiB, Concurrency=256`

**Note**: Full test suite with 10 sizes × 8 concurrency levels = 80 tests
- At 1 minute per test: ~1.5 hours total
- Consider reducing test duration or number of combinations for faster results

### Quick Test (Smaller Matrix)
To run a faster test, edit `run_warp.sh`:
```bash
# Smaller test matrix
SIZES=(1KiB 256KiB 4MiB 64MiB)
CONCURRENCIES=(1 64 512 2048)
DUR="30s"
```

## Analyzing Results

After tests complete:
```bash
python3 analyze_results.py results_YYYYMMDD_HHMMSS/
```

This generates:
1. **Charts** (saved to `results_*/charts/`):
   - `throughput_heatmap.png` - Performance across all configurations
   - `throughput_by_size.png` - How throughput varies with object size
   - `throughput_by_concurrency.png` - How throughput scales with concurrency
   - `ops_by_size.png` - Operations per second analysis
   - `latency_analysis.png` - Latency patterns
   - `optimal_configurations.png` - Top 10 best configurations

2. **Summary Report** (`performance_summary.txt`):
   - Best overall configuration
   - Best configuration per object size
   - Performance breakdown analysis
   - Identification of performance degradation points

## Understanding Results

### Key Metrics
- **Throughput (MB/s)**: Data transfer rate - higher is better
- **Operations/sec**: Number of operations completed - higher is better for small objects
- **Latency (ms)**: Response time - lower is better

### What to Look For

1. **Optimal Configuration**: The size/concurrency combination with highest throughput
2. **Performance Scaling**: How performance improves with concurrency
3. **Breakdown Point**: Where adding more concurrency hurts performance
4. **Sweet Spots**: Configurations that balance throughput and resource usage

### Typical Patterns

- **Small objects** (< 1MiB): Higher concurrency often helps, ops/sec matters more
- **Large objects** (> 10MiB): Throughput saturates at lower concurrency
- **Breakdown**: Usually occurs when server/network becomes saturated

## Example Workflow

```bash
# 1. Configure credentials
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."

# 2. Run tests (go get coffee ☕)
./run_warp.sh

# 3. Analyze results
python3 analyze_results.py results_20251111_143000/

# 4. View charts
open results_20251111_143000/charts/

# 5. Read summary
cat results_20251111_143000/charts/performance_summary.txt
```

## Customization

### Test Different Operations
Currently tests `PUT` operations. To test `GET`:
```bash
# In run_warp.sh, change:
./warp put \
# to:
./warp get \
```

### Add More Metrics
Edit `analyze_results.py` to parse additional warp output fields.

### Custom Size Ranges
```bash
# For very small objects:
SIZES=(100B 1KiB 10KiB 100KiB)

# For very large objects:
SIZES=(10MiB 50MiB 100MiB 500MiB 1GiB)
```

## Troubleshooting

### No results found
- Check that `.log` files exist in results directory
- Verify warp binary is executable and in correct location
- Check AWS credentials are set

### Charts not generating
- Install missing Python packages: `pip3 install matplotlib numpy`
- Check Python version: `python3 --version` (need 3.7+)

### Tests failing
- Check network connectivity to S3 endpoint
- Verify bucket exists or uncomment bucket creation line in script
- Check AWS credentials have proper permissions
- Review individual test logs for specific errors

### Performance seems wrong
- Ensure no other heavy processes are running
- Check network bandwidth isn't saturated
- Verify S3 service isn't rate-limiting
- Consider multiple test runs for consistency

## Tips

1. **Start small**: Run a quick test with fewer combinations first
2. **Monitor resources**: Watch CPU, memory, network during tests
3. **Multiple runs**: Run critical configurations multiple times for accuracy
4. **Document findings**: Note any environmental factors affecting results
5. **Baseline comparison**: Save results over time to track performance changes

## License

This is a testing suite wrapper around MinIO warp. See [MinIO warp license](https://github.com/minio/warp).
