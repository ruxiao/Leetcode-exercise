// SPDX-License-Identifier: MIT
pragma solidity ^0.8.18; // Use a recent Solidity version

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol"; // Optional: for minting control

contract DesciCoin is ERC20, Ownable {
    constructor(uint256 initialSupply) ERC20("DesciCoin", "DSC") {
        // Mint initialSupply to the deployer of the contract
        // The deployer can then distribute these tokens as needed (e.g., to a treasury, for bounties etc.)
        if (initialSupply > 0) {
            _mint(msg.sender, initialSupply * (10**decimals()));
        }
    }

    // Function to allow the owner to mint more tokens if needed (e.g., for future inflation, rewards)
    // This is optional and depends on the desired tokenomics. For simplicity, it can be omitted initially.
    function mint(address to, uint256 amount) public onlyOwner {
        _mint(to, amount);
    }
}
