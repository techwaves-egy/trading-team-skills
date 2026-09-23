# AI Autonomous Trading Firm — Agent Operational Directives (AGENTS.md)

## 📌 Mandatory Version Control & GitHub Protocol

All AI assistants and agents operating on this repository MUST strictly follow these rules:

### 1. Continuous GitHub Synchronization
* **Commit on Every Completed Task:** Never leave modified code uncommitted. Immediately after implementing and verifying changes, stage and commit with clear semantic commit messages (`feat:`, `fix:`, `docs:`, `chore:`).
* **Immediate Remote Push:** Always push commits to the private remote repository (`origin master`):
  ```bash
  git push origin master
  ```

### 2. Milestone Tagging & Rollback Guarantee
* **Create Semantic Tags:** For every architectural milestone, feature set, or release, create an annotated Git tag:
  ```bash
  git tag -a v3.8.x -m "v3.8.x: Description of milestone"
  git push origin --tags
  ```
* **Preserve Revertability:** Maintain clean commit history so the user can instantly inspect or revert to any prior tag (`v3.8.0-stable`, `v3.8.1`, etc.):
  ```bash
  # Check out previous tag
  git checkout <tag>

  # Or hard reset if requested
  git reset --hard <tag>
  python scripts/skill_integrity_guard.py --authorize
  ```

### 3. Cryptographic Integrity Guard (Anti-Tamper)
* **Protected Files:** `SKILL.md`, `scripts/*.py`, `docs/*.md`.
* **Manifest Re-Certification:** If any protected file is modified, re-sign the cryptographic manifest before committing:
  ```bash
  python scripts/skill_integrity_guard.py --authorize
  ```
* **Verify Zero Violations:** Always confirm `python scripts/skill_integrity_guard.py` outputs `[OK] All protected skill and engine files are 100% verified`.

### 4. Admin Security Isolation
* All anti-tamper warnings, authorization tokens, and `/approve` commands MUST route **strictly and exclusively** to Administrator `@wtalaat` (`chat_id: 1264076025`).
* Never broadcast sensitive tokens or internal exceptions to the public VIP Signals channel (`-1003989306390`).
