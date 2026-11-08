# staking-rewards-sim

A staking rewards simulator in pure Python — a faithful port of the classic
Synthetix `StakingRewards` contract, the reward-distribution model behind
most DeFi liquidity-mining programs.

Users stake a token and reward tokens accrue pro-rata over a fixed rewards
duration. All arithmetic is integer math with 1e18 fixed-point precision,
exactly like the Solidity version. Time is an explicit integer (seconds)
passed to every mutating call, so the whole thing is deterministic and easy
to test — no wall clock, no chain needed.

## Features

- `reward_per_token()` — accumulated reward per staked token (1e18-scaled)
- `earned(account, now)` — rewards accrued by an account up to `now`
- `stake()` / `withdraw()` / `get_reward()` / `exit()` — the full staking flow
- `notify_reward_amount()` — fund a new rewards period; leftover rewards
  from a still-running period roll into the new one instead of being lost
- Late joiners only earn from the moment they stake, and rewards stop
  accruing at `period_finish`

## Usage

```python
from staking import StakingRewards

pool = StakingRewards(rewards_duration=100)  # 100-second rewards period
pool.notify_reward_amount(reward=1000, now=0)  # 10 reward tokens / second
pool.stake("alice", 100, now=0)
pool.stake("bob", 300, now=0)

pool.earned("alice", now=50)   # 125 — 25% of the 500 tokens emitted so far
pool.earned("bob", now=50)     # 375

pool.get_reward("alice", now=100)  # 250
pool.get_reward("bob", now=100)    # 750
```

## Run

```bash
python3 staking.py            # demo: two stakers, one rewards period
python3 staking.py --test     # doctests
```

Zero dependencies, Python 3.8+.
