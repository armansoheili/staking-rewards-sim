"""Staking rewards simulator in pure Python.

A faithful port of the classic Synthetix ``StakingRewards`` contract
(``contracts/StakingRewards.sol``) — the reward-distribution model behind
most DeFi liquidity-mining programs. Users stake a token, and reward
tokens accrue pro-rata over a fixed rewards duration.

All arithmetic is integer math with 1e18 fixed-point precision, exactly
like the Solidity version. Time is an explicit integer (seconds) passed
to every mutating call, so the whole thing is deterministic and easy to
test — no wall clock, no chain needed.

Usage:
    >>> from staking import StakingRewards
    >>> pool = StakingRewards(rewards_duration=100)
    >>> pool.notify_reward_amount(reward=1000, now=0)
    >>> pool.stake("alice", 100, now=0)
    >>> pool.earned("alice", now=50)
    500
    >>> pool.get_reward("alice", now=100)
    1000

The reward rate is ``reward / duration`` per second, split across all
stakers in proportion to their stake, so a lone staker earns everything.
"""

PRECISION = 10 ** 18


class StakingRewards:
    """A single staking pool distributing one reward token."""

    def __init__(self, rewards_duration=7 * 24 * 3600):
        self.rewards_duration = rewards_duration
        self.period_finish = 0
        self.reward_rate = 0
        self.last_update_time = 0
        self.reward_per_token_stored = 0
        self.total_supply = 0
        self.balances = {}
        self.user_reward_per_token_paid = {}
        self.rewards = {}

    # -- views ---------------------------------------------------------

    def last_time_reward_applicable(self, now):
        """Last second rewards still accrue at (capped at period end)."""
        return min(now, self.period_finish)

    def reward_per_token(self, now):
        """Accumulated reward per staked token, scaled by 1e18.

        >>> pool = StakingRewards(rewards_duration=100)
        >>> pool.notify_reward_amount(reward=1000, now=0)
        >>> pool.stake("alice", 100, now=0)
        >>> pool.reward_per_token(now=10)
        1000000000000000000
        """
        if self.total_supply == 0:
            return self.reward_per_token_stored
        elapsed = self.last_time_reward_applicable(now) - self.last_update_time
        return self.reward_per_token_stored + (
            elapsed * self.reward_rate * PRECISION // self.total_supply
        )

    def earned(self, account, now):
        """Rewards accrued by ``account`` up to ``now`` (not yet claimed).

        >>> pool = StakingRewards(rewards_duration=100)
        >>> pool.notify_reward_amount(reward=1000, now=0)
        >>> pool.stake("alice", 100, now=0)
        >>> pool.stake("bob", 300, now=0)
        >>> pool.earned("alice", now=50), pool.earned("bob", now=50)
        (125, 375)
        """
        per_token = self.reward_per_token(now)
        paid = self.user_reward_per_token_paid.get(account, 0)
        balance = self.balances.get(account, 0)
        return balance * (per_token - paid) // PRECISION + self.rewards.get(account, 0)

    # -- internal ------------------------------------------------------

    def _update_reward(self, account, now):
        self.reward_per_token_stored = self.reward_per_token(now)
        self.last_update_time = self.last_time_reward_applicable(now)
        if account is not None:
            self.rewards[account] = self.earned(account, now)
            self.user_reward_per_token_paid[account] = self.reward_per_token_stored

    # -- actions -------------------------------------------------------

    def notify_reward_amount(self, reward, now):
        """Fund a new rewards period of ``reward`` tokens starting at ``now``.

        If a period is still running, the leftover rewards roll into the
        new period instead of being lost.

        >>> pool = StakingRewards(rewards_duration=100)
        >>> pool.notify_reward_amount(reward=1000, now=0)
        >>> pool.reward_rate
        10
        >>> pool.notify_reward_amount(reward=500, now=50)
        >>> pool.reward_rate  # (500 remaining + 500 new) / 100
        10
        """
        self._update_reward(None, now)
        if now >= self.period_finish:
            self.reward_rate = reward // self.rewards_duration
        else:
            remaining = (self.period_finish - now) * self.reward_rate
            self.reward_rate = (reward + remaining) // self.rewards_duration
        self.last_update_time = now
        self.period_finish = now + self.rewards_duration

    def stake(self, account, amount, now):
        """Stake ``amount`` tokens for ``account``.

        >>> pool = StakingRewards(rewards_duration=100)
        >>> pool.notify_reward_amount(reward=1000, now=0)
        >>> pool.stake("alice", 100, now=0)
        >>> pool.total_supply
        100
        >>> pool.stake("alice", 0, now=0)
        Traceback (most recent call last):
        ...
        ValueError: cannot stake 0
        """
        if amount <= 0:
            raise ValueError("cannot stake 0")
        self._update_reward(account, now)
        self.total_supply += amount
        self.balances[account] = self.balances.get(account, 0) + amount

    def withdraw(self, account, amount, now):
        """Withdraw ``amount`` of staked tokens.

        >>> pool = StakingRewards(rewards_duration=100)
        >>> pool.notify_reward_amount(reward=1000, now=0)
        >>> pool.stake("alice", 100, now=0)
        >>> pool.withdraw("alice", 40, now=10)
        >>> pool.balances["alice"], pool.total_supply
        (60, 60)
        >>> pool.withdraw("alice", 100, now=10)
        Traceback (most recent call last):
        ...
        ValueError: insufficient staked balance
        """
        if amount > self.balances.get(account, 0):
            raise ValueError("insufficient staked balance")
        self._update_reward(account, now)
        self.total_supply -= amount
        self.balances[account] -= amount

    def get_reward(self, account, now):
        """Claim all accrued rewards for ``account``; returns the amount.

        >>> pool = StakingRewards(rewards_duration=100)
        >>> pool.notify_reward_amount(reward=1000, now=0)
        >>> pool.stake("alice", 100, now=0)
        >>> pool.stake("bob", 100, now=0)
        >>> pool.get_reward("alice", now=100)
        500
        >>> pool.earned("alice", now=100)
        0
        >>> pool.get_reward("bob", now=100)
        500
        """
        self._update_reward(account, now)
        reward = self.rewards.get(account, 0)
        if reward > 0:
            self.rewards[account] = 0
        return reward

    def exit(self, account, now):
        """Withdraw everything and claim rewards in one call.

        >>> pool = StakingRewards(rewards_duration=100)
        >>> pool.notify_reward_amount(reward=1000, now=0)
        >>> pool.stake("alice", 100, now=0)
        >>> pool.exit("alice", now=100)
        1000
        >>> pool.balances["alice"], pool.total_supply
        (0, 0)
        """
        self.withdraw(account, self.balances.get(account, 0), now)
        return self.get_reward(account, now)


def demo():
    """Two stakers, one 100-second period, 1000 reward tokens."""
    pool = StakingRewards(rewards_duration=100)
    pool.notify_reward_amount(reward=1000, now=0)
    pool.stake("alice", 100, now=0)
    pool.stake("bob", 300, now=0)
    print("reward rate per second:", pool.reward_rate)
    print("alice earned at t=50:  ", pool.earned("alice", now=50))
    print("bob earned at t=50:    ", pool.earned("bob", now=50))
    print("alice claims at t=100: ", pool.get_reward("alice", now=100))
    print("bob claims at t=100:   ", pool.get_reward("bob", now=100))
    # Late staker joins halfway through: rewards split from then on.
    pool2 = StakingRewards(rewards_duration=100)
    pool2.notify_reward_amount(reward=1000, now=0)
    pool2.stake("alice", 100, now=0)
    pool2.stake("bob", 100, now=50)
    print("late join — alice:", pool2.get_reward("alice", now=100),
          "bob:", pool2.get_reward("bob", now=100))


if __name__ == "__main__":
    import sys

    if "--test" in sys.argv:
        import doctest

        failures, _ = doctest.testmod(verbose=False)
        raise SystemExit(1 if failures else 0)
    demo()
