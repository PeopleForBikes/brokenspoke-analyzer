# Caching

Depending on how you use the analyzer and how frequently, caching the files
downloaded from the internet can be very beneficial and substantially reduce the
time spent for preparing the analysis.

Here is a flowchart depicting the process:

```{graphviz}
digraph Flowchart {
    rankdir=LR;
    node [shape=rectangle, style=filled, fillcolor=lightgray];

    A [label="File Request"];
    B [label="Cached?", shape=diamond, fillcolor=white];
    D [label="Download into cache"];
    F [label="Copy to Store"];
    G [label="Processing?", shape=diamond, fillcolor=white];
    H [label="Process"];
    K [label="Done"];

    A -> B;
    B -> F [label="Yes"];
    B -> D [label="No"];
    D -> F;
    F -> G;
    G -> H [label="Yes"];
    G -> K [label="No"];
    H -> K;
}
```

The following files will be cached:

- US 2020 Census blocks
- US 2022 LODES data (employment)
- US Water blocks
- US State speed limits
- US City speed limits

```{important}
The brokenspoke-analyzer does not perform any cache management operation, like
invalidating the cache or cleaning up the files. This is the user's
responsability to ensure the content of the cache is up to date.
```

## Caching strategies

The brokenspoke analyzer provides several caching strategies:

- No cache
- User cache directory
- AWS S3 Bucket

The cache is configured using environment variables only.

```{attention}
Environment variables are case sensitive. If the value is incorrect, it falls
back to the "no cache" strategy.
```

### No cache (default)

By default, the brokenspoke-analyzer does not cache any data. It simply stores
them in the `output directory` specified by the user via the `--output-dir`
option (by default it is `./data`).

However if the files already exist in the `output directory`, then they won't be
redownloaded.

If you use the analyzer occasionally for only one or two cities, this strategy
is most likely the best match.

### User cache directory

For users running multiple or frequent analyses, this is the recomended caching
strategy.

Files will be downloaded and stored in the user cache directory for future uses,
speeding up the data ingestion phase.

Depending on the platform, the user cache directory will be one of the
following:

- OSX: `~/Library/Application Support/brokenspoke-analyzer`
- Linux: `~/.local/share/brokenspoke-analyzer`
- Windows:
  `C:\Documents and Settings\<User>\Application Data\Local Settings\PeopleForBikes\brokenspoke-analyzer`

To use it, set the following environment variable:

```bash
export BNA_CACHING_STRATEGY=USER_CACHE
```

### AWS S3 bucket

When using the brokenspoke-analyzer in the AWS cloud there is the possibility to
cache them in an S3 bucket.

The bucket name (i.e. wthout the `s3://` scheme) and the AWS region of the
account must be specified.

To use it, set the following environment variables:

```bash
export BNA_CACHING_STRATEGY=AWS_S3
export BNA_CACHE_AWS_S3_BUCKET=my-aws-cache-bucket
export AWS_REGION=us-east-1
```
