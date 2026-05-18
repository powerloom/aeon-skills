# On-Chain CID Verification

Every BDS response includes a `verification` object. The `cid` is the content identifier of the consensus-finalized snapshot stored on IPFS. You can verify it against the Powerloom blockchain.

## Verification Object

```json
{
  "verification": {
    "cid": "bafkrei...",
    "epoch": 24785842,
    "projectId": "allTradesSnapshot:0x4198...",
    "dataMarket": "0x4198Bf81B55EE4Af6f9Ddc176F8021960813f641",
    "protocolState": "0xa1100CB00Acd3cA83a7C8F4DAA42701D1Eaf4A6c"
  }
}
```

## Verify with cast (Foundry)

```bash
cast call 0xa1100CB00Acd3cA83a7C8F4DAA42701D1Eaf4A6c \
  "maxSnapshotsCid(address,string,uint256)(string,uint8)" \
  0x4198Bf81B55EE4Af6f9Ddc176F8021960813f641 \
  "<projectId>" \
  <epoch> \
  --rpc-url https://rpc-v2.powerloom.network
```

Returns: `(cid_string, status_code)`
- `status_code = 0`: CID exists and matches
- `status_code = 1`: CID mismatch
- `status_code = 2`: No snapshot for this epoch

## Contract Addresses

| Contract | Address | Chain |
|----------|---------|-------|
| ProtocolState | `0xa1100CB00Acd3cA83a7C8F4DAA42701D1Eaf4A6c` | Powerloom |
| DataMarket (BDS) | `0x4198Bf81B55EE4Af6f9Ddc176F8021960813f641` | Powerloom |

## RPC URL

```
https://rpc-v2.powerloom.network
```

## Verification in Python

```python
from web3 import Web3

w3 = Web3(Web3.HTTPProvider("https://rpc-v2.powerloom.network"))

protocol_state = "0xa1100CB00Acd3cA83a7C8F4DAA42701D1Eaf4A6c"
data_market = "0x4198Bf81B55EE4Af6f9Ddc176F8021960813f641"

abi = '[{"inputs":[{"name":"dataMarket","type":"address"},{"name":"projectId","type":"string"},{"name":"epochId","type":"uint256"}],"name":"maxSnapshotsCid","outputs":[{"name":"","type":"string"},{"name":"","type":"uint8"}],"stateMutability":"view","type":"function"}]'

contract = w3.eth.contract(address=protocol_state, abi=abi)

def verify_cid(project_id: str, epoch: int, expected_cid: str) -> bool:
    cid, status = contract.functions.maxSnapshotsCid(
        data_market, project_id, epoch
    ).call()
    return cid == expected_cid and status == 0
```

## Why Verification Matters

1. **Consensus-finalized**: The data was validated by the DSV network
2. **Tamper-proof**: CID is stored on-chain, can't be changed retroactively
3. **Auditable**: Anyone can verify, no trust required
4. **Provenance**: Every alert carries its own receipt

## Verification in bds-agent

The `bds-agent run` command supports `verify: true` in `agent.yaml`:

```yaml
name: my-agent
source:
  type: bds_stream
  endpoint: /mpp/stream/allTrades
auth:
  api_key: ${BDS_API_KEY}
verify: true  # Auto-verify CIDs on each event
verify_rpc_url: https://rpc-v2.powerloom.network
```

On mismatch, the runner logs a warning and sends a `verification` rule alert.
