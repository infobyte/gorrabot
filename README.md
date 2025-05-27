# Gorrabot

*GitLab bot that automates Faraday’s workflow checks and issue hygiene.*

---

## Table of Contents

1. [Features](#features)

   1. [CHANGELOG check](#changelog-check)
   2. [Issue ↔ MR status sync](#issue-state-sync)
   3. [Field auto‑completion](#field-auto)
   4. [Branch‑naming check](#branch-naming)
   5. [MR title check](#title-check)
   6. [Upper‑version MR automation](#upper-mr)
   7. [Slack reporting](#slack-report)
2. [Special labels](#special-labels)
3. [Deployment](#deployment)

   1. [AWS architecture](#aws-arch)
   2. [SSH access](#ssh)
4. [Design goals](#design-goals)

---

## <a name="features"></a>Features

### <a name="changelog-check"></a>1 · CHANGELOG check

By default every MR **must** add a `.md` entry inside `CHANGELOG/<current_version>/`.
If the MR lacks such change, Gorrabot marks it **WIP** and asks the author to
update it (unless the `no‑changelog` label is present).

### <a name="issue-state-sync"></a>2 · Issue ↔ MR status sync

Gorrabot infers the related issue from the branch name and keeps issue labels
in sync with MR state:

| MR state                | Issue label action            |
| ----------------------- | ----------------------------- |
| WIP/Draft               | `accepted`                    |
| Open (ready for review) | `test`                        |
| Merged                  | Close and clear status labels |
| Closed (unmerged)       | Clear status labels           |

### <a name="field-auto"></a>3 · Field auto‑completion

Missing assignee or milestone? Gorrabot copies them from the linked issue.

### <a name="branch-naming"></a>4 · Branch‑naming check

Warns (non‑blocking) if branch name deviates from our `tkt_*`/`sup_*`/`exp_*`
conventions.

### <a name="title-check"></a>5 · MR title check

Titles inherited from the branch (`Tkt community 1234 …`) trigger a friendly
comment suggesting a concise human title.

### <a name="upper-mr"></a>6 · Upper‑version MR automation

For multi‑edition work (Community → Professional → Enterprise) Gorrabot auto‑creates
and wires follow‑up MRs, notifying the author when manual action is needed.

### <a name="slack-report"></a>7 · Slack reporting

Scheduled digests report:

* Stale MRs (WIP & non‑WIP)
* Excessive `accepted` backlog
* Issues blocked waiting for a decision
  Individual devs get personal to‑do lists; `REPORT_USERS` get a team summary.

---

## <a name="special-labels"></a>Special labels

| Label                     | Effect                                      |
| ------------------------- | ------------------------------------------- |
| `no-changelog`            | Skip CHANGELOG enforcement                  |
| `multiple-merge-requests` | Disable issue–MR status sync                |
| `sacate-la-gorra`         | Disable **all** Gorrabot checks for that MR |
| `waiting-decision`        | Triggers decision‑waiting reminders         |

---

## <a name="deployment"></a>Deployment

### <a name="aws-arch"></a>AWS architecture

| Component                  | Value                                                                         |
| -------------------------- | ----------------------------------------------------------------------------- |
| **Account (prod)**         | `471112768198`                                                                |
| **Elastic Beanstalk env.** | `gorrabot-dev` [(public URL)](http://gorrabot.us-east-1.elasticbeanstalk.com) |
| **VPC**                    | `vpc-07607b18eac7ff529` (`gorrabot-vpc`)                                      |
| **Platform**               | AL2 Docker *v2* with Launch Templates                                         |

> The environment lives in a dedicated VPC, isolated from other Faraday
> workloads.

### <a name="ssh"></a>SSH access

1. **Open port 22** on the Security Group attached to the *gorrabot-dev* Auto
   Scaling group (preferably restricted to your source IP).
2. Retrieve the private key from **AWS Secrets Manager**:

   ```bash
   aws secretsmanager get-secret-value \
     --secret-id gorrabotkey \
     --query SecretString --output text > ~/.ssh/gorrabotkey
   chmod 600 ~/.ssh/gorrabotkey
   ```
3. Connect to the instance (Elastic IP **3.225.208.31**):

   ```bash
   ssh -i ~/.ssh/gorrabotkey ec2-user@3.225.208.31
   ```

The public key is already in `~/.ssh/authorized_keys` on the instance.

---

## <a name="design-goals"></a>Design goals

### Avoid state

Stateless by design: Gorrabot re‑queries GitLab instead of persisting data.
Small downsides (duplicate comments after wording changes) are acceptable for
simpler ops.

### Don't replace CI

Gorrabot focuses on workflow automation; build/test pipelines remain the job of
CI.

---

© Infobyte LLC · Licensed under GPL v3
