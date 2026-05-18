# BDS API Reference

**Base URL**: `https://bds.powerloom.io/api`

## Authentication

All `/mpp/...` endpoints require Bearer authentication:

```http
Authorization: Bearer sk_live_...
```

Get your API key at https://bds-metering.powerloom.io/metering

## Key Endpoints

### Trades

| Endpoint | Description |
|----------|-------------|
| `GET /mpp/snapshot/allTrades` | Latest trades across all pools (no path param) |
| `GET /mpp/snapshot/allTrades/{epoch}` | Trades for specific epoch (integer block number) |
| `GET /mpp/snapshot/trades/{pool}` | Trades for specific pool |
| `GET /mpp/stream/allTrades` | SSE stream of all trades |

**Note**: Use `/mpp/snapshot/allTrades` without any path parameter for latest. The `{block_number}` variant requires an integer epoch, not "latest".

### Token Data

| Endpoint | Description |
|----------|-------------|
| `GET /mpp/token/{address}/pools` | Pools containing a token |
| `GET /mpp/token/price/{token}/{pool}` | Token price in a pool |
| `GET /mpp/tokenPrices/all/{chain}` | All token prices |

### Market Data

| Endpoint | Description |
|----------|-------------|
| `GET /mpp/ethPrice` | Current ETH price |
| `GET /mpp/tradeVolume/{pool}/{window}` | Trade volume for pool |
| `GET /mpp/dailyActiveTokens` | Tokens with recent activity |
| `GET /mpp/dailyActivePools` | Pools with recent activity |

### Time Series

| Endpoint | Description |
|----------|-------------|
| `GET /mpp/timeSeries/ethPrice?window=1h` | ETH price history |

## Response Format

```json
{
  "epoch": 24785842,
  "data": [...],
  "verification": {
    "cid": "bafkrei...",
    "epoch": 24785842,
    "projectId": "allTradesSnapshot:0x26c4...",
    "dataMarket": "0x26c44e5CcEB7Fe69Cffc933838CF40286b2dc01a",
    "protocolState": "0x1d0e010Ff11b781CA1dE34BD25a0037203e25E2a"
  }
}
```

## Credit Balance

Check your balance in the `X-BDS-Credit-Balance` response header.

## Rate Limits

- Streaming: 1 session at a time per API key
- Snapshot: Rate-limited per endpoint
- 402 response = insufficient credits

## Full Catalog

See: https://bds.powerloom.io/api/endpoints.json
