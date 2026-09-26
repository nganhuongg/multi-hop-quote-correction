// SPDX-License-Identifier: MIT
pragma solidity 0.8.29;

import {Test} from "forge-std/Test.sol";
import {IPoolManager} from "@uniswap/v4-core/src/interfaces/IPoolManager.sol";
import {IUnlockCallback} from "@uniswap/v4-core/src/interfaces/callback/IUnlockCallback.sol";
import {PoolKey} from "@uniswap/v4-core/src/types/PoolKey.sol";
import {PoolId, PoolIdLibrary} from "@uniswap/v4-core/src/types/PoolId.sol";
import {Currency} from "@uniswap/v4-core/src/types/Currency.sol";
import {IHooks} from "@uniswap/v4-core/src/interfaces/IHooks.sol";
import {Hooks} from "@uniswap/v4-core/src/libraries/Hooks.sol";
import {TickMath} from "@uniswap/v4-core/src/libraries/TickMath.sol";
import {BalanceDelta, BalanceDeltaLibrary} from "@uniswap/v4-core/src/types/BalanceDelta.sol";
import {ModifyLiquidityParams, SwapParams} from "@uniswap/v4-core/src/types/PoolOperation.sol";
import {PoolModifyLiquidityTest} from "@uniswap/v4-core/src/test/PoolModifyLiquidityTest.sol";
import {V4Quoter} from "@uniswap/v4-periphery/src/lens/V4Quoter.sol";
import {IV4Quoter} from "@uniswap/v4-periphery/src/interfaces/IV4Quoter.sol";
import {PathKey} from "@uniswap/v4-periphery/src/libraries/PathKey.sol";
import {MockTIP20} from "v4-hooks-public/test/aggregator-hooks/TempoExchange/mocks/MockTIP20.sol";
import {MockTempoExchange} from "v4-hooks-public/test/aggregator-hooks/TempoExchange/mocks/MockTempoExchange.sol";
import {TempoExchangeAggregator} from "v4-hooks-public/src/aggregator-hooks/implementations/TempoExchange/TempoExchangeAggregator.sol";
import {ITempoExchange} from "v4-hooks-public/src/aggregator-hooks/implementations/TempoExchange/interfaces/ITempoExchange.sol";
import {HookMiner} from "v4-hooks-public/src/utils/HookMiner.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/// A deliberately small, independent hook rule: subtract exactly 100 output units.
/// Its fee is transferred from PoolManager to the hook; the router never calculates it.
contract FixedOutputFeeHook {
    using BalanceDeltaLibrary for BalanceDelta;

    IPoolManager public immutable manager;
    bool public enabled;
    uint256 public calls;
    uint256 public collected;
    uint128 public constant FEE = 100;

    error WrongHookData();
    error FeeExceedsOutput();

    constructor(IPoolManager _manager) { manager = _manager; }

    function setEnabled(bool value) external { enabled = value; }

    function afterSwap(address, PoolKey calldata key, SwapParams calldata params, BalanceDelta delta, bytes calldata hookData)
        external returns (bytes4, int128)
    {
        require(msg.sender == address(manager), "only PoolManager");
        if (keccak256(hookData) != keccak256(hex"42")) revert WrongHookData();
        calls++;
        if (!enabled) return (IHooks.afterSwap.selector, 0);

        int128 output = params.zeroForOne ? delta.amount1() : delta.amount0();
        if (output <= int128(FEE)) revert FeeExceedsOutput();
        Currency outputCurrency = params.zeroForOne ? key.currency1 : key.currency0;
        manager.take(outputCurrency, address(this), FEE);
        collected += FEE;
        return (IHooks.afterSwap.selector, int128(FEE));
    }
}

/// One unlock, all hops, one initial settlement and one final take.
/// This executes real PoolManager.swap and hook callbacks; it is a diagnostic router,
/// not UniRoute's unavailable production calldata builder.
contract ExactInPathRouter is IUnlockCallback {
    using BalanceDeltaLibrary for BalanceDelta;

    IPoolManager public immutable manager;
    error InvalidPath();
    error PartialFill(uint256 spent, uint256 required);
    error TooLittleReceived(uint256 received, uint256 minimum);

    constructor(IPoolManager _manager) { manager = _manager; }

    struct Job {
        address payer;
        address recipient;
        address tokenIn;
        uint128 amountIn;
        PoolKey[] keys;
        bytes[] hookData;
    }

    function swapExactIn(PoolKey[] calldata keys, bytes[] calldata hookData, address tokenIn, uint128 amountIn, uint128 minimum)
        external returns (uint256 amountOut)
    {
        if (keys.length == 0 || keys.length != hookData.length) revert InvalidPath();
        Job memory job = Job(msg.sender, msg.sender, tokenIn, amountIn, keys, hookData);
        amountOut = abi.decode(manager.unlock(abi.encode(job)), (uint256));
        if (amountOut < minimum) revert TooLittleReceived(amountOut, minimum);
    }

    function unlockCallback(bytes calldata payload) external returns (bytes memory) {
        require(msg.sender == address(manager), "only PoolManager");
        Job memory job = abi.decode(payload, (Job));
        Currency input = Currency.wrap(job.tokenIn);
        uint256 amount = job.amountIn;

        // Front-load exactly the caller's input, as an actual full transaction can.
        manager.sync(input);
        require(IERC20(job.tokenIn).transferFrom(job.payer, address(manager), amount), "input transfer");
        manager.settle();

        for (uint256 i; i < job.keys.length; i++) {
            PoolKey memory key = job.keys[i];
            bool zeroForOne;
            Currency output;
            if (input == key.currency0) { zeroForOne = true; output = key.currency1; }
            else if (input == key.currency1) { zeroForOne = false; output = key.currency0; }
            else revert InvalidPath();

            BalanceDelta delta = manager.swap(
                key,
                SwapParams({
                    zeroForOne: zeroForOne,
                    amountSpecified: -int256(amount),
                    sqrtPriceLimitX96: zeroForOne ? TickMath.MIN_SQRT_PRICE + 1 : TickMath.MAX_SQRT_PRICE - 1
                }),
                job.hookData[i]
            );
            uint256 spent = uint256(uint128(-(zeroForOne ? delta.amount0() : delta.amount1())));
            if (spent != amount) revert PartialFill(spent, amount);
            amount = uint256(uint128(zeroForOne ? delta.amount1() : delta.amount0()));
            input = output;
        }
        manager.take(input, job.recipient, amount);
        return abi.encode(amount);
    }
}

contract QuoteRegressionTest is Test {
    using PoolIdLibrary for PoolKey;

    uint160 constant SQRT_PRICE_1_1 = 79228162514264337593543950336;
    uint128 constant MEDIUM = 1_000_000;
    uint160 constant FEE_FLAGS = Hooks.AFTER_SWAP_FLAG | Hooks.AFTER_SWAP_RETURNS_DELTA_FLAG;
    bytes constant FEE_DATA = hex"42";

    IPoolManager manager;
    V4Quoter quoter;
    ExactInPathRouter router;
    PoolModifyLiquidityTest lp;
    MockTIP20 tokenA;
    MockTIP20 tokenB;
    MockTIP20 tokenC;
    FixedOutputFeeHook h1;
    FixedOutputFeeHook h2;
    address alice = address(0xA11CE);

    function setUp() public {
        manager = IPoolManager(deployCode("/Users/harry/uniswap-v4-study/v4-core/out/PoolManager.sol/PoolManager.json", abi.encode(address(0))));
        quoter = new V4Quoter(manager);
        router = new ExactInPathRouter(manager);
        lp = new PoolModifyLiquidityTest(manager);
        tokenA = new MockTIP20("A", "A", 6, address(0));
        tokenB = new MockTIP20("B", "B", 6, address(tokenA));
        tokenC = new MockTIP20("C", "C", 6, address(0));
        _fund(tokenA); _fund(tokenB); _fund(tokenC);
        h1 = _feeHook(1);
        h2 = _feeHook(2);
    }

    function _fund(MockTIP20 token) internal {
        token.mint(address(this), 1_000_000_000_000);
        token.mint(alice, 1_000_000_000_000);
        token.approve(address(lp), type(uint256).max);
        vm.prank(alice);
        token.approve(address(router), type(uint256).max);
    }

    function _feeHook(uint160 index) internal returns (FixedOutputFeeHook hook) {
        FixedOutputFeeHook implementation = new FixedOutputFeeHook(manager);
        address hookAddress = address(uint160(0x1000000000000000000000000000000000000000) + (index << 16) + FEE_FLAGS);
        vm.etch(hookAddress, address(implementation).code);
        hook = FixedOutputFeeHook(hookAddress);
        hook.setEnabled(true);
    }

    function _key(address x, address y, IHooks hook) internal pure returns (PoolKey memory) {
        (address a, address b) = x < y ? (x, y) : (y, x);
        return PoolKey(Currency.wrap(a), Currency.wrap(b), 0, 60, hook);
    }

    function _makePool(address x, address y, IHooks hook, bool provideLiquidity) internal returns (PoolKey memory key) {
        key = _key(x, y, hook);
        manager.initialize(key, SQRT_PRICE_1_1);
        if (provideLiquidity) {
            lp.modifyLiquidity(key, ModifyLiquidityParams({tickLower: -600, tickUpper: 600, liquidityDelta: 1_000_000_000, salt: 0}), "");
        }
    }

    function _paths(PoolKey memory first, bytes memory d0) internal pure returns (PoolKey[] memory keys, bytes[] memory data) {
        keys = new PoolKey[](1); data = new bytes[](1); keys[0] = first; data[0] = d0;
    }

    function _paths(PoolKey memory first, bytes memory d0, PoolKey memory second, bytes memory d1)
        internal pure returns (PoolKey[] memory keys, bytes[] memory data)
    {
        keys = new PoolKey[](2); data = new bytes[](2);
        keys[0] = first; keys[1] = second; data[0] = d0; data[1] = d1;
    }

    function _quote(PoolKey[] memory keys, bytes[] memory data, address tokenIn, uint128 amount)
        internal returns (uint256 output, uint256 quoteGas)
    {
        PathKey[] memory path = new PathKey[](keys.length);
        Currency current = Currency.wrap(tokenIn);
        for (uint256 i; i < keys.length; i++) {
            PoolKey memory key = keys[i];
            Currency next = current == key.currency0 ? key.currency1 : key.currency0;
            path[i] = PathKey(next, key.fee, key.tickSpacing, key.hooks, data[i]);
            current = next;
        }
        vm.prank(alice);
        return quoter.quoteExactInput(IV4Quoter.QuoteExactParams(Currency.wrap(tokenIn), path, amount));
    }

    function _execute(PoolKey[] memory keys, bytes[] memory data, address tokenIn, uint128 amount)
        internal returns (uint256 output, uint256 gasUsed)
    {
        uint256 beforeGas = gasleft();
        vm.prank(alice);
        output = router.swapExactIn(keys, data, tokenIn, amount, 1);
        gasUsed = beforeGas - gasleft();
        emit log_named_uint("full router gas", gasUsed);
    }

    function _assertQuoteExecution(PoolKey[] memory keys, bytes[] memory data, address tokenIn, uint128 amount)
        internal returns (uint256 output)
    {
        (uint256 quoted,) = _quote(keys, data, tokenIn, amount);
        (output,) = _execute(keys, data, tokenIn, amount);
        emit log_named_uint("quote output", quoted);
        emit log_named_uint("execution output", output);
        assertEq(quoted, output, "quote must equal full transaction output");
    }

    function test_A_single_no_hook() public {
        PoolKey memory ab = _makePool(address(tokenA), address(tokenB), IHooks(address(0)), true);
        (PoolKey[] memory keys, bytes[] memory data) = _paths(ab, "");
        _assertQuoteExecution(keys, data, address(tokenA), MEDIUM);
    }

    function test_B_two_no_hooks() public {
        PoolKey memory ab = _makePool(address(tokenA), address(tokenB), IHooks(address(0)), true);
        PoolKey memory bc = _makePool(address(tokenB), address(tokenC), IHooks(address(0)), true);
        (PoolKey[] memory keys, bytes[] memory data) = _paths(ab, "", bc, "");
        _assertQuoteExecution(keys, data, address(tokenA), MEDIUM);
    }

    function test_C_single_fee_hook_fee_off_on_same_snapshot() public {
        PoolKey memory ab = _makePool(address(tokenA), address(tokenB), IHooks(address(h1)), true);
        (PoolKey[] memory keys, bytes[] memory data) = _paths(ab, FEE_DATA);
        h1.setEnabled(false);
        uint256 checkpoint = vm.snapshotState();
        uint256 off = _assertQuoteExecution(keys, data, address(tokenA), MEDIUM);
        vm.revertToState(checkpoint);
        h1.setEnabled(true);
        uint256 on = _assertQuoteExecution(keys, data, address(tokenA), MEDIUM);
        assertEq(off - on, 100, "independent fixed fee check");
        assertEq(tokenB.balanceOf(address(h1)), 100, "actual fee transfer");
        assertEq(h1.calls(), 1);
    }

    function test_D_fee_hook_first() public {
        PoolKey memory ab = _makePool(address(tokenA), address(tokenB), IHooks(address(h1)), true);
        PoolKey memory bc = _makePool(address(tokenB), address(tokenC), IHooks(address(0)), true);
        (PoolKey[] memory keys, bytes[] memory data) = _paths(ab, FEE_DATA, bc, "");
        h1.setEnabled(false);
        uint256 checkpoint = vm.snapshotState();
        uint256 off = _assertQuoteExecution(keys, data, address(tokenA), MEDIUM);
        vm.revertToState(checkpoint);
        h1.setEnabled(true);
        uint256 on = _assertQuoteExecution(keys, data, address(tokenA), MEDIUM);
        assertGt(off, on, "first-leg fee must affect final output");
        assertEq(tokenB.balanceOf(address(h1)), 100);
        assertEq(h1.calls(), 1);
    }

    function test_E_fee_hook_last() public {
        PoolKey memory ca = _makePool(address(tokenC), address(tokenA), IHooks(address(0)), true);
        PoolKey memory ab = _makePool(address(tokenA), address(tokenB), IHooks(address(h1)), true);
        (PoolKey[] memory keys, bytes[] memory data) = _paths(ca, "", ab, FEE_DATA);
        h1.setEnabled(false);
        uint256 checkpoint = vm.snapshotState();
        uint256 off = _assertQuoteExecution(keys, data, address(tokenC), MEDIUM);
        vm.revertToState(checkpoint);
        h1.setEnabled(true);
        uint256 on = _assertQuoteExecution(keys, data, address(tokenC), MEDIUM);
        assertEq(off - on, 100, "last-leg fee is 100 output units");
        assertEq(tokenB.balanceOf(address(h1)), 100);
        assertEq(h1.calls(), 1);
    }

    function test_F_two_fee_hooks() public {
        PoolKey memory ab = _makePool(address(tokenA), address(tokenB), IHooks(address(h1)), true);
        PoolKey memory bc = _makePool(address(tokenB), address(tokenC), IHooks(address(h2)), true);
        (PoolKey[] memory keys, bytes[] memory data) = _paths(ab, FEE_DATA, bc, FEE_DATA);
        h1.setEnabled(false); h2.setEnabled(false);
        uint256 checkpoint = vm.snapshotState();
        uint256 off = _assertQuoteExecution(keys, data, address(tokenA), MEDIUM);
        vm.revertToState(checkpoint);
        h1.setEnabled(true); h2.setEnabled(true);
        uint256 on = _assertQuoteExecution(keys, data, address(tokenA), MEDIUM);
        assertGt(off, on, "both fees must affect final output");
        assertEq(tokenB.balanceOf(address(h1)), 100);
        assertEq(tokenC.balanceOf(address(h2)), 100);
        assertEq(h1.calls(), 1); assertEq(h2.calls(), 1);
    }

    function test_custom_hook_wrong_hook_data_fails_both_paths() public {
        PoolKey memory ab = _makePool(address(tokenA), address(tokenB), IHooks(address(h1)), true);
        (PoolKey[] memory keys, bytes[] memory data) = _paths(ab, "");
        vm.expectRevert();
        _quote(keys, data, address(tokenA), MEDIUM);
        vm.prank(alice);
        vm.expectRevert();
        router.swapExactIn(keys, data, address(tokenA), MEDIUM, 1);
    }

    function _tempo() internal returns (TempoExchangeAggregator hook, MockTempoExchange exchange, PoolKey memory ab) {
        exchange = new MockTempoExchange();
        exchange.addSupportedPair(address(tokenA), address(tokenB));
        tokenA.mint(address(exchange), 1_000_000_000_000);
        tokenB.mint(address(exchange), 1_000_000_000_000);
        uint160 flags = Hooks.BEFORE_SWAP_FLAG | Hooks.BEFORE_SWAP_RETURNS_DELTA_FLAG
            | Hooks.BEFORE_INITIALIZE_FLAG | Hooks.BEFORE_ADD_LIQUIDITY_FLAG;
        bytes memory args = abi.encode(address(manager), address(exchange));
        (address wanted, bytes32 salt) = HookMiner.find(address(this), flags, type(TempoExchangeAggregator).creationCode, args);
        hook = new TempoExchangeAggregator{salt: salt}(manager, ITempoExchange(address(exchange)));
        assertEq(address(hook), wanted);
        ab = _makePool(address(tokenA), address(tokenB), IHooks(address(hook)), false);
    }

    function test_G_single_tempo_direct_quote_and_router() public {
        (TempoExchangeAggregator hook,, PoolKey memory ab) = _tempo();
        (PoolKey[] memory keys, bytes[] memory data) = _paths(ab, "");
        bool zeroForOne = ab.currency0 == Currency.wrap(address(tokenA));
        vm.prank(alice);
        uint256 direct = hook.quote(zeroForOne, -int256(uint256(MEDIUM)), ab.toId());
        assertEq(tokenA.balanceOf(address(manager)), 0, "no hidden manager seed");
        vm.expectRevert();
        _quote(keys, data, address(tokenA), MEDIUM);
        (uint256 executed,) = _execute(keys, data, address(tokenA), MEDIUM);
        emit log_named_uint("direct hook quote", direct);
        emit log_named_uint("execution output", executed);
        assertEq(direct, executed);
    }

    function test_H_tempo_first_quoter_fails_but_router_succeeds() public {
        (TempoExchangeAggregator hook,, PoolKey memory ab) = _tempo();
        PoolKey memory bc = _makePool(address(tokenB), address(tokenC), IHooks(address(0)), true);
        (PoolKey[] memory keys, bytes[] memory data) = _paths(ab, "", bc, "");
        assertEq(tokenA.balanceOf(address(manager)), 0, "no hidden manager seed");
        bool zeroForOne = ab.currency0 == Currency.wrap(address(tokenA));
        vm.prank(alice);
        uint256 firstLegCandidate = hook.quote(zeroForOne, -int256(uint256(MEDIUM)), ab.toId());
        assertGt(firstLegCandidate, 0);
        // Diagnostic candidate only: quote the second leg against the same initial state.
        // The assertion below against one full transaction is what validates it here.
        vm.prank(alice);
        (uint256 composedCandidate,) = quoter.quoteExactInputSingle(
            IV4Quoter.QuoteExactSingleParams({
                poolKey: bc,
                zeroForOne: bc.currency0 == Currency.wrap(address(tokenB)),
                exactAmount: uint128(firstLegCandidate),
                hookData: ""
            })
        );
        vm.expectRevert();
        _quote(keys, data, address(tokenA), MEDIUM);
        (uint256 executed,) = _execute(keys, data, address(tokenA), MEDIUM);
        emit log_named_uint("first-leg candidate", firstLegCandidate);
        emit log_named_uint("composed candidate", composedCandidate);
        emit log_named_uint("execution output", executed);
        assertEq(composedCandidate, executed, "candidate must be checked against full execution");
        assertGt(executed, 0);
    }

    function test_H_tempo_last_quoter_and_router() public {
        (TempoExchangeAggregator hook,, PoolKey memory ab) = _tempo();
        PoolKey memory ca = _makePool(address(tokenC), address(tokenA), IHooks(address(0)), true);
        (PoolKey[] memory keys, bytes[] memory data) = _paths(ca, "", ab, "");
        emit log_named_uint("manager A before quote", tokenA.balanceOf(address(manager)));
        uint256 output = _assertQuoteExecution(keys, data, address(tokenC), MEDIUM);
        assertGt(output, 0);
        assertGt(address(hook).code.length, 0);
    }

    function test_no_hook_genuine_insufficient_liquidity() public {
        PoolKey memory ab = _makePool(address(tokenA), address(tokenB), IHooks(address(0)), true);
        (PoolKey[] memory keys, bytes[] memory data) = _paths(ab, "");
        uint128 huge = 1_000_000_000_000;
        vm.expectRevert();
        _quote(keys, data, address(tokenA), huge);
        vm.prank(alice);
        vm.expectRevert();
        router.swapExactIn(keys, data, address(tokenA), huge, 1);
    }

    function test_H_tempo_first_four_amounts_without_manager_seed() public {
        (, , PoolKey memory ab) = _tempo();
        PoolKey memory bc = _makePool(address(tokenB), address(tokenC), IHooks(address(0)), true);
        (PoolKey[] memory keys, bytes[] memory data) = _paths(ab, "", bc, "");
        uint256 base = vm.snapshotState();
        // The B/C liquidity deposit leaves about 29.55 million B in PoolManager;
        // 25 million is deliberately near that fixture reserve, not an arbitrary "large" label.
        uint128[4] memory amounts = [uint128(1_000), uint128(1_000_000), uint128(10_000_000), uint128(25_000_000)];
        for (uint256 i; i < amounts.length; i++) {
            vm.revertToState(base);
            assertEq(tokenA.balanceOf(address(manager)), 0);
            vm.expectRevert();
            _quote(keys, data, address(tokenA), amounts[i]);
            (uint256 output,) = _execute(keys, data, address(tokenA), amounts[i]);
            emit log_named_uint("amount", amounts[i]);
            emit log_named_uint("execution output, no manager seed", output);
            assertGt(output, 0);
        }
    }

    function test_H_tempo_first_explicit_manager_seed_diagnostic() public {
        (, , PoolKey memory ab) = _tempo();
        PoolKey memory bc = _makePool(address(tokenB), address(tokenC), IHooks(address(0)), true);
        (PoolKey[] memory keys, bytes[] memory data) = _paths(ab, "", bc, "");
        assertEq(tokenA.balanceOf(address(manager)), 0);
        // Diagnostic override ONLY: explicit source is a mock-token mint to PoolManager.
        // The quote and router execution below both start from this same seeded state.
        tokenA.mint(address(manager), MEDIUM);
        emit log_named_uint("explicit manager A seed", MEDIUM);
        _assertQuoteExecution(keys, data, address(tokenA), MEDIUM);
    }
}
