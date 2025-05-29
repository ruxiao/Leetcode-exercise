# DeSci Verifier - Tokenomics and Bounty Mechanism (Phase 2 Design - Part 1)

This document outlines the initial design for the tokenomics and bounty mechanism for the DeSci Verifier platform. This is a living document and will evolve as the platform develops.

## 1. Native Platform Token: DesciCoin (DSC)

*   **Name:** DesciCoin
*   **Symbol:** DSC (example symbol)
*   **Type:** ERC20 token on a compatible blockchain (e.g., Ethereum, Polygon).

### 1.1. Token Utility

The DesciCoin will serve multiple purposes within the ecosystem:

*   **Bounty Posting:** DSC is the primary currency used by Researchers (or other users) to fund verification bounties for their scientific code and results.
*   **Verifier Rewards:** Verifiers earn DSC for successfully completing and submitting verification tasks that are approved.
*   **Staking (Future):**
    *   Verifiers may be required to stake DSC to participate in verification tasks. This stake can act as a security deposit, disincentivizing malicious behavior.
    *   The amount of stake could influence the Verifier's reputation or their probability of being selected for certain bounties.
*   **Governance (Future):**
    *   DSC holders will be able to participate in the governance of the platform, voting on protocol upgrades, parameter changes (e.g., platform fees), and dispute resolution frameworks.
*   **Platform Fees:** A small percentage of bounty amounts might be collected in DSC and directed to a platform treasury.

## 2. Bounty Lifecycle

The process for verifying scientific work through a bounty will generally follow these steps:

1.  **Bounty Creation:**
    *   A **Researcher** (or any entity wanting to validate a piece of work) defines a verification task. This includes:
        *   A link to the Git repository (and specific commit hash).
        *   The execution script and parameters (as defined in the MVP's `config.json`).
        *   Clear success criteria and expected outputs.
        *   An IPFS hash pointing to a detailed document containing all verification requirements, datasets (or links/hashes to them), and any other relevant information.
    *   The Researcher locks a predetermined amount of `DesciCoin` into the `BountyContract` to fund the bounty.

2.  **Bounty Discovery:**
    *   Open bounties are listed and discoverable by potential **Verifiers**. This could be via a platform UI or by querying the `BountyContract` directly.

3.  **Verification Work (Claim/Execution - Simplified Initial Model):**
    *   A Verifier (or multiple, depending on the model chosen) signals their intent to work on a bounty.
    *   **Initial Model:** For simplicity, we might start with a model where multiple Verifiers can attempt a bounty, and the first one to submit a correct and approved verification is rewarded.
    *   **Future Models:** Could involve Verifiers staking DSC to claim a bounty exclusively, or auction mechanisms for high-value bounties.
    *   The Verifier uses the DeSci Verifier tool (the MVP codebase) to execute the code in a reproducible environment and generate a verification report.

4.  **Verification Submission:**
    *   The Verifier submits their results, which includes:
        *   The detailed verification report (logs, outputs, file checks) – potentially uploaded to IPFS, with the hash submitted to the `BountyContract`.
        *   A statement of whether the verification met the defined success criteria.

5.  **Approval and Reward Distribution:**
    *   The **Researcher** (or bounty creator) reviews the Verifier's submitted report.
    *   If the verification is deemed successful and meets all requirements, the Researcher approves the submission.
    *   Upon approval, the `BountyContract` automatically releases the locked `DesciCoin` to the successful Verifier's address.
    *   **Initial Simplification:** For the first iteration of the smart contract, the "approval" might be an admin-triggered function after off-chain confirmation to simplify the contract logic. This can be decentralized later.

6.  **Dispute Resolution (Placeholder for Future Design):**
    *   If a Researcher rejects a Verifier's submission, or if there's any disagreement, a dispute resolution mechanism will be necessary.
    *   This could involve:
        *   A panel of trusted, highly-staked Verifiers who vote on the outcome.
        *   A decentralized court system (e.g., Kleros).
        *   The specifics will be designed in a later iteration.

## 3. Verifier Incentives (Initial)

*   **Direct Bounty Rewards:** The primary incentive is earning `DesciCoin` from bounties.
*   **Reputation Building:** Successful verifications (recorded on-chain and linked to a Verifier's address/DID) will contribute to their reputation. A higher reputation may grant access to more complex or higher-value bounties, or a larger share of rewards in pooled verification tasks.

## 4. Platform Fees (Initial)

*   To ensure sustainable development and maintenance of the DeSci Verifier platform, a small percentage (e.g., 1-5%) of each bounty amount could be automatically transferred to a platform treasury when the bounty is paid out.
*   The usage of these treasury funds would ideally be governed by `DesciCoin` holders in the future.

## 5. Next Steps

*   Develop the `DesciCoin.sol` (ERC20) and `BountyContract.sol` smart contracts.
*   Develop backend services to interact with these contracts.
*   Integrate basic bounty creation/listing features into the user interface (CLI initially, then web).
