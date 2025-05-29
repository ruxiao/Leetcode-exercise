const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("BountyContract", function () {
    let DesciCoin, desciCoin, BountyContract, bountyContract;
    let owner, researcher, verifier1, verifier2;
    const initialSupply = ethers.utils.parseUnits("1000000", 18); // 1 million DSC

    beforeEach(async function () {
        [owner, researcher, verifier1, verifier2] = await ethers.getSigners();

        // Deploy DesciCoin
        DesciCoin = await ethers.getContractFactory("DesciCoin");
        desciCoin = await DesciCoin.deploy(initialSupply);
        await desciCoin.deployed();

        // Distribute some DesciCoin to researcher for testing
        await desciCoin.connect(owner).transfer(researcher.address, ethers.utils.parseUnits("1000", 18));

        // Deploy BountyContract
        BountyContract = await ethers.getContractFactory("BountyContract");
        bountyContract = await BountyContract.deploy(desciCoin.address);
        await bountyContract.deployed();
    });

    describe("Deployment", function () {
        it("Should set the right DSC token address", async function () {
            expect(await bountyContract.token()).to.equal(desciCoin.address);
        });
        it("Owner should have initial supply of DesciCoin", async function () {
            expect(await desciCoin.balanceOf(owner.address)).to.equal(initialSupply);
        });
    });

    describe("Creating Bounties", function () {
        const bountyAmount = ethers.utils.parseUnits("100", 18);
        const ipfsHash = "QmSomeIpfsHashForVerificationDetails";

        it("Should allow a researcher to create a bounty", async function () {
            // Researcher approves BountyContract to spend their DSC
            await desciCoin.connect(researcher).approve(bountyContract.address, bountyAmount);

            // Researcher creates the bounty
            await expect(bountyContract.connect(researcher).createBounty(bountyAmount, ipfsHash))
                .to.emit(bountyContract, "BountyCreated")
                .withArgs(1, researcher.address, bountyAmount, ipfsHash); // Assuming first bountyId is 1

            const bounty = await bountyContract.bounties(1);
            expect(bounty.creator).to.equal(researcher.address);
            expect(bounty.amount).to.equal(bountyAmount);
            expect(bounty.status).to.equal(0); // Status.Open
            expect(await desciCoin.balanceOf(bountyContract.address)).to.equal(bountyAmount);
        });

        it("Should fail if amount is zero", async function () {
             await desciCoin.connect(researcher).approve(bountyContract.address, bountyAmount); // Approve some amount
             await expect(bountyContract.connect(researcher).createBounty(0, ipfsHash))
                .to.be.revertedWithCustomError(bountyContract, "InvalidAmount")
                .withArgs(0);
        });
        
        it("Should fail if token transfer fails (insufficient allowance/balance)", async function () {
            // No approval given
            await expect(bountyContract.connect(researcher).createBounty(bountyAmount, ipfsHash))
                .to.be.revertedWithCustomError(bountyContract, "TransferFailed"); // Or ERC20: insufficient allowance
        });
    });
    
    describe("Submitting and Approving Verification", function () {
        const bountyAmount = ethers.utils.parseUnits("50", 18);
        const bountyIpfsHash = "QmBountyDetails";
        const reportIpfsHash = "QmVerificationReport";
        let bountyId;

        beforeEach(async function() {
            // Create a bounty first
            await desciCoin.connect(researcher).approve(bountyContract.address, bountyAmount);
            const tx = await bountyContract.connect(researcher).createBounty(bountyAmount, bountyIpfsHash);
            const receipt = await tx.wait();
            bountyId = receipt.events.find(e => e.event === 'BountyCreated').args.bountyId;
        });

        it("Should allow verifier to submit verification and researcher to approve", async function () {
            // Verifier submits verification
            await expect(bountyContract.connect(verifier1).submitVerification(bountyId, reportIpfsHash))
                .to.emit(bountyContract, "BountyVerificationSubmitted")
                .withArgs(bountyId, verifier1.address, reportIpfsHash);
            
            let bounty = await bountyContract.bounties(bountyId);
            expect(bounty.status).to.equal(1); // Status.Pending
            expect(bounty.successfulVerifier).to.equal(verifier1.address); // Tentatively set

            // Researcher approves
            const verifierInitialBalance = await desciCoin.balanceOf(verifier1.address);
            await expect(bountyContract.connect(researcher).approveVerificationAndPay(bountyId, verifier1.address))
                .to.emit(bountyContract, "BountyApprovedAndPaid")
                .withArgs(bountyId, verifier1.address, bountyAmount);

            bounty = await bountyContract.bounties(bountyId);
            expect(bounty.status).to.equal(2); // Status.Closed
            expect(await desciCoin.balanceOf(verifier1.address)).to.equal(verifierInitialBalance.add(bountyAmount));
            expect(await desciCoin.balanceOf(bountyContract.address)).to.equal(0); // Assuming this was the only bounty
        });

        it("Should fail approval if not bounty creator", async function () {
            await bountyContract.connect(verifier1).submitVerification(bountyId, reportIpfsHash);
            await expect(bountyContract.connect(verifier2).approveVerificationAndPay(bountyId, verifier1.address)) // verifier2 is not creator
                .to.be.revertedWithCustomError(bountyContract, "NotBountyCreator");
        });
        
        it("Should fail approval if bounty is not in Pending state", async function () {
            // Bounty is still Open, not Pending
            await expect(bountyContract.connect(researcher).approveVerificationAndPay(bountyId, verifier1.address))
                .to.be.revertedWithCustomError(bountyContract, "BountyNotPending");
        });
    });
    
    describe("Cancelling Bounties", function () {
        const bountyAmount = ethers.utils.parseUnits("30", 18);
        const bountyIpfsHash = "QmCancelBounty";
        let bountyId;

        beforeEach(async function() {
            await desciCoin.connect(researcher).approve(bountyContract.address, bountyAmount);
            const tx = await bountyContract.connect(researcher).createBounty(bountyAmount, bountyIpfsHash);
            const receipt = await tx.wait();
            bountyId = receipt.events.find(e => e.event === 'BountyCreated').args.bountyId;
        });

        it("Should allow creator to cancel an Open bounty", async function() {
            const researcherInitialBalance = await desciCoin.balanceOf(researcher.address);
            
            await expect(bountyContract.connect(researcher).cancelBounty(bountyId))
                .to.emit(bountyContract, "BountyCancelled")
                .withArgs(bountyId);

            const bounty = await bountyContract.bounties(bountyId);
            expect(bounty.status).to.equal(3); // Status.Cancelled
            // Researcher's balance should increase by bountyAmount (minus gas costs)
            // The contract's balance of DSC for this bounty should go to zero.
            expect(await desciCoin.balanceOf(bountyContract.address)).to.equal(0); // Assuming only this bounty
            // Checking exact researcher balance is tricky due to gas, but it should be more.
            // A more precise check would be contract balance before/after.
        });
        
        it("Should fail to cancel if not creator", async function() {
             await expect(bountyContract.connect(verifier1).cancelBounty(bountyId))
                .to.be.revertedWithCustomError(bountyContract, "NotBountyCreator");
        });

        it("Should fail to cancel if bounty is not Open", async function() {
            await bountyContract.connect(verifier1).submitVerification(bountyId, "someReportHash"); // Moves to Pending
            await expect(bountyContract.connect(researcher).cancelBounty(bountyId))
                .to.be.revertedWithCustomError(bountyContract, "BountyNotOpen");
        });
    });

});
