"""Tests for branch ownership and cross-agent coordination."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.coordination import BranchClaim, BranchClaims


@pytest.fixture
def claims(tmp_path: Path) -> BranchClaims:
    return BranchClaims(path=tmp_path / "branch_claims.jsonl")


@pytest.fixture
def sample_claim() -> BranchClaim:
    return BranchClaim(
        branch="auth-refactor",
        agent_name="aider",
        pid=7702,
        claimed_at="2026-05-07T12:00:00+00:00",
    )


class TestBranchClaim:
    def test_frozen(self, sample_claim: BranchClaim) -> None:
        with pytest.raises(AttributeError):
            sample_claim.branch = "main"  # type: ignore[misc]

    def test_round_trip_dict(self, sample_claim: BranchClaim) -> None:
        restored = BranchClaim.from_dict(sample_claim.to_dict())
        assert restored == sample_claim

    def test_from_dict_missing_claimed_at(self) -> None:
        claim = BranchClaim.from_dict({"branch": "main", "agent_name": "aider", "pid": 1234})
        assert claim.branch == "main"
        assert claim.agent_name == "aider"
        assert claim.pid == 1234
        assert claim.claimed_at  # auto-populated

    def test_from_dict_coerces_types(self) -> None:
        claim = BranchClaim.from_dict({"branch": "main", "agent_name": "codex", "pid": "9999"})
        assert claim.pid == 9999
        assert isinstance(claim.pid, int)


class TestBranchClaims:
    def test_claim_and_get(self, claims: BranchClaims, sample_claim: BranchClaim) -> None:
        result = claims.claim(sample_claim.branch, sample_claim.agent_name, sample_claim.pid)
        assert result is not None
        assert result.branch == sample_claim.branch
        assert result.agent_name == sample_claim.agent_name
        assert result.pid == sample_claim.pid

        retrieved = claims.get(sample_claim.branch)
        assert retrieved == result

    def test_claim_returns_none_on_conflict(self, claims: BranchClaims) -> None:
        claims.claim("main", "aider", 7702)
        result = claims.claim("main", "claude-code", 8421)
        assert result is None

    def test_claim_same_agent_same_branch_updates(self, claims: BranchClaims) -> None:
        first = claims.claim("main", "aider", 7702)
        assert first is not None
        second = claims.claim("main", "aider", 7702)
        assert second is not None
        assert claims.get("main") == second

    def test_release_removes_claim(self, claims: BranchClaims, sample_claim: BranchClaim) -> None:
        claims.claim(sample_claim.branch, sample_claim.agent_name, sample_claim.pid)
        removed = claims.release(sample_claim.branch)
        assert removed is not None
        assert removed.branch == sample_claim.branch
        assert claims.get(sample_claim.branch) is None

    def test_release_nonexistent_returns_none(self, claims: BranchClaims) -> None:
        assert claims.release("nonexistent") is None

    def test_is_held(self, claims: BranchClaims) -> None:
        assert not claims.is_held("main")
        claims.claim("main", "aider", 7702)
        assert claims.is_held("main")

    def test_holder_returns_agent_name(self, claims: BranchClaims) -> None:
        claims.claim("main", "aider", 7702)
        assert claims.holder("main") == "aider"
        assert claims.holder("nonexistent") is None

    def test_holder_pid_returns_pid(self, claims: BranchClaims) -> None:
        claims.claim("main", "aider", 7702)
        assert claims.holder_pid("main") == 7702
        assert claims.holder_pid("nonexistent") is None

    def test_list_returns_all_claims(self, claims: BranchClaims) -> None:
        claims.claim("main", "aider", 7702)
        claims.claim("dev", "claude-code", 8421)
        listed = claims.list()
        assert len(listed) == 2
        branches = {c.branch for c in listed}
        assert branches == {"main", "dev"}

    def test_persistence_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "branch_claims.jsonl"
        reg1 = BranchClaims(path=path)
        reg1.claim("main", "aider", 7702)
        reg1.claim("dev", "claude-code", 8421)

        reg2 = BranchClaims(path=path)
        assert len(reg2.list()) == 2
        assert reg2.holder("main") == "aider"
        assert reg2.holder("dev") == "claude-code"

    def test_release_updates_disk(self, tmp_path: Path) -> None:
        path = tmp_path / "branch_claims.jsonl"
        reg1 = BranchClaims(path=path)
        reg1.claim("main", "aider", 7702)
        reg1.claim("dev", "claude-code", 8421)
        reg1.release("main")

        reg2 = BranchClaims(path=path)
        assert len(reg2.list()) == 1
        assert reg2.holder("main") is None
        assert reg2.holder("dev") == "claude-code"

    def test_jsonl_file_format(self, tmp_path: Path) -> None:
        path = tmp_path / "branch_claims.jsonl"
        reg = BranchClaims(path=path)
        reg.claim("main", "aider", 7702)

        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["branch"] == "main"
        assert parsed["agent_name"] == "aider"
        assert parsed["pid"] == 7702

    def test_corrupt_line_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "branch_claims.jsonl"
        path.write_text(
            '{"branch":"main","agent_name":"aider","pid":7702,"claimed_at":"2026-05-07T12:00:00+00:00"}\n'
            "this is not json\n"
            '{"branch":"dev","agent_name":"claude-code","pid":8421,"claimed_at":"2026-05-07T12:00:00+00:00"}\n',
            encoding="utf-8",
        )
        reg = BranchClaims(path=path)
        assert len(reg.list()) == 2

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "branch_claims.jsonl"
        path.write_text("", encoding="utf-8")
        reg = BranchClaims(path=path)
        assert reg.list() == []

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        path = tmp_path / "does_not_exist.jsonl"
        reg = BranchClaims(path=path)
        assert reg.list() == []

    def test_claim_same_branch_different_pid_is_conflict(self, claims: BranchClaims) -> None:
        """Same agent name but different PID should be treated as a conflict."""
        claims.claim("main", "aider", 7702)
        result = claims.claim("main", "aider", 9999)  # Same name, different PID
        assert result is None

    def test_claim_different_agent_same_pid_is_conflict(self, claims: BranchClaims) -> None:
        """Different agent name but same PID - this is unlikely but still a conflict."""
        claims.claim("main", "aider", 7702)
        result = claims.claim("main", "claude-code", 7702)  # Different name, same PID
        assert result is None
