// SPDX-License-Identifier: MIT
pragma solidity ^0.8.18;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol"; // Corrected path for OpenZeppelin v4.x+
import "@openzeppelin/contracts/utils/Counters.sol"; // For generating unique bounty IDs

contract BountyContract is ReentrancyGuard {
    using Counters for Counters.Counter;

    Counters.Counter private _bountyIds;

    IERC20 public immutable token; // The token used for bounties (e.g., DesciCoin)

    struct Bounty {
        uint256 id;
        address creator;
        uint256 amount;
        string verificationDetailsIpfsHash; // IPFS hash pointing to detailed requirements
        address assignedVerifier; // Initially null, can be assigned
        address successfulVerifier; // The verifier whose submission was approved
        Status status;
        // uint256 createdAt; // Timestamp for creation
        // uint256 expiresAt; // Optional: bounty expiration
    }

    enum Status {
        Open,      // Bounty is open for verifiers
        Pending,   // Verification submitted, pending approval
        Closed,    // Bounty paid out or cancelled
        Cancelled  // Bounty cancelled by creator (if allowed)
    }

    mapping(uint256 => Bounty) public bounties;

    event BountyCreated(uint256 indexed bountyId, address indexed creator, uint256 amount, string verificationDetailsIpfsHash);
    event BountyVerificationSubmitted(uint256 indexed bountyId, address indexed verifier, string verificationReportIpfsHash); // Example event
    event BountyApprovedAndPaid(uint256 indexed bountyId, address indexed verifier, uint256 amount);
    event BountyCancelled(uint256 indexed bountyId);

    // --- Errors ---
    error BountyNotFound(uint256 bountyId);
    error NotBountyCreator(uint256 bountyId, address caller);
    error InvalidAmount(uint256 amount);
    error BountyNotOpen(uint256 bountyId);
    error BountyNotPending(uint256 bountyId);
    error TransferFailed();
    error CallerNotAssignedVerifier(uint256 bountyId, address caller); // If we implement assignment

    constructor(address tokenAddress) {
        require(tokenAddress != address(0), "Token address cannot be zero");
        token = IERC20(tokenAddress);
    }

    function createBounty(uint256 amount, string calldata verificationDetailsIpfsHash) external nonReentrant returns (uint256) {
        if (amount == 0) revert InvalidAmount(amount);

        _bountyIds.increment();
        uint256 newBountyId = _bountyIds.current();

        // Transfer tokens from the bounty creator to this contract
        bool success = token.transferFrom(msg.sender, address(this), amount);
        if (!success) revert TransferFailed();

        bounties[newBountyId] = Bounty({
            id: newBountyId,
            creator: msg.sender,
            amount: amount,
            verificationDetailsIpfsHash: verificationDetailsIpfsHash,
            assignedVerifier: address(0), // No specific verifier assigned initially
            successfulVerifier: address(0),
            status: Status.Open
            // createdAt: block.timestamp
        });

        emit BountyCreated(newBountyId, msg.sender, amount, verificationDetailsIpfsHash);
        return newBountyId;
    }
    
    // Placeholder for verifier submitting their work - actual logic can be more complex
    // For now, this just marks it as Pending. A more robust system would link to the verifier's report.
    function submitVerification(uint256 bountyId, string calldata verificationReportIpfsHash) external nonReentrant {
        Bounty storage bounty = bounties[bountyId];
        if (bounty.id == 0) revert BountyNotFound(bountyId); // Check if bounty exists
        if (bounty.status != Status.Open) revert BountyNotOpen(bountyId);
        // Optional: Check if msg.sender is an allowed/assigned verifier
        // if (bounty.assignedVerifier != address(0) && bounty.assignedVerifier != msg.sender) {
        //     revert CallerNotAssignedVerifier(bountyId, msg.sender);
        // }

        bounty.status = Status.Pending;
        bounty.successfulVerifier = msg.sender; // Tentatively set, assuming this verifier's submission is the one being reviewed

        emit BountyVerificationSubmitted(bountyId, msg.sender, verificationReportIpfsHash);
    }


    function approveVerificationAndPay(uint256 bountyId, address verifierAddress) external nonReentrant {
        Bounty storage bounty = bounties[bountyId];

        if (bounty.id == 0) revert BountyNotFound(bountyId);
        if (msg.sender != bounty.creator) revert NotBountyCreator(bountyId, msg.sender); // Only creator can approve
        if (bounty.status != Status.Pending) revert BountyNotPending(bountyId); // Must be pending approval
        if (verifierAddress == address(0)) revert("Verifier address cannot be zero");


        bounty.status = Status.Closed;
        bounty.successfulVerifier = verifierAddress; // Confirm the verifier

        bool success = token.transfer(bounty.successfulVerifier, bounty.amount);
        if (!success) revert TransferFailed();

        emit BountyApprovedAndPaid(bountyId, bounty.successfulVerifier, bounty.amount);
    }
    
    // Optional: Allow creator to cancel an Open bounty and retrieve funds
    function cancelBounty(uint256 bountyId) external nonReentrant {
        Bounty storage bounty = bounties[bountyId];
        if (bounty.id == 0) revert BountyNotFound(bountyId);
        if (msg.sender != bounty.creator) revert NotBountyCreator(bountyId, msg.sender);
        if (bounty.status != Status.Open) revert BountyNotOpen(bountyId); // Can only cancel Open bounties

        bounty.status = Status.Cancelled;
        
        bool success = token.transfer(bounty.creator, bounty.amount);
        if (!success) {
            // If transfer fails, should we revert the status change? 
            // This situation should ideally not happen if the contract holds the tokens.
            // For now, emit event and leave status as Cancelled. Consider implications.
            emit TransferFailed(); // A more specific event might be better
        }
        emit BountyCancelled(bountyId);
    }

    // --- View Functions ---
    function getBounty(uint256 bountyId) external view returns (Bounty memory) {
        if (bounties[bountyId].id == 0) revert BountyNotFound(bountyId);
        return bounties[bountyId];
    }
    
    function getBountyCount() external view returns (uint256) {
        return _bountyIds.current();
    }
}
