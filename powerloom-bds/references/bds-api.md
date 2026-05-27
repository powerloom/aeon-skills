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
| `GET /mpp/snapshot/allTrades` | Latest finalized epoch only (no `from_epoch` query) |
| `GET /mpp/snapshot/allTrades/{epoch}` | **Use this for catch-up** — one block per request |
| `GET /mpp/snapshot/trades/{pool}` | Trades for specific pool |
| `GET /mpp/stream/allTrades` | SSE firehose — not used by Aeon whale-radar skill |

**Aeon whale-radar:** loop `{epoch}` from `lastStreamEpoch+1` via `scripts/fetch-bds-epochs.py`. Do not pass `from_epoch` on bare snapshot GET.

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
  "epoch": { "begin": 24785842, "end": 24785842 },
  "tradeData": {
    "0xPoolAddress": {
      "trades": [ { "tradeType": "Swap", "data": { "calculated_trade_amount_usd": "1234.56" }, "log": { ... } } ]
    }
  },
  "verification": {
    "cid": "bafkrei...",
    "epochId": 24785842,
    "projectId": "allTradesSnapshot:0x4198...:mainnet-..."
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
