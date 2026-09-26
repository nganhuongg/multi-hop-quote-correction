# Tempo: use case thật cho ngưỡng mất quote multi-hop

Kiểm tra 2026-09-26, chain **4217**. Không gửi giao dịch lên Tempo, không sửa production, không chạy lại 13 test của `REPORT.md`. “Execution” dưới đây là `eth_call`/`debug_traceCall` của **Universal Router deployment thật**; với ca fork, trạng thái đã thay đổi được ghi riêng.

| Use case | Quote hiện tại | Universal Router, output thực | Phương án thay thế | Lợi ích sau gas | Mức chứng cứ |
|---|---:|---:|---|---|---|
| Đối chứng một chặng cUSD→PathUSD, 5.249475 cUSD, parent block 41,183,156 | `hook.quote`: 5.248425 PathUSD | 5.248425; receipt gas 206,811 | — | — | Tx lịch sử status=1, replay `eth_call` ở parent block |
| cUSD→PathUSD→USDT0, 1 cUSD, block 41,183,156 | 0.999899 USDT0 | 0.999899; gas 323,356 | chưa xác nhận | chưa đo | RPC thật, cùng block/caller, 2 hook trong trace |
| cUSD→PathUSD→USDC.e, 1 cUSD, block 41,183,156 | 0.999800 USDC.e | 0.999800; gas 312,156 | chưa xác nhận | chưa đo | RPC thật, cùng block/caller, 2 hook trong trace |
| USDC.e→PathUSD→USDT0, 1 USDC.e, block 41,115,563 | 1.000000 USDT0 | 1.000000; gas 585,524 | chưa xác nhận | chưa đo | RPC thật; Permit2 signature lịch sử được tái dùng; 2 hook |
| USDC.e→PathUSD→cUSD, 1 USDC.e, block 41,115,563 | 0.999800 cUSD | 0.999800; gas 578,524 | chưa xác nhận | chưa đo | RPC thật; Permit2 signature lịch sử được tái dùng; 2 hook |
| **U1/U3:** cUSD→PathUSD→USDT0, **19.862460 cUSD**, block 41,183,156 | **revert** tại `PoolManager.take(cUSD)` | **19.860473 USDT0**, gas **571,946**, nếu Universal Router thực hiện `SETTLE` trước `SWAP`; lệnh `SWAP` rồi `SETTLE` cũng revert | chưa xác nhận | chưa đo | Fork có **chỉ cấp cUSD cho ví thử nghiệm**; PM/DEX giữ nguyên |
| Đối chứng thiếu thanh khoản thật, 1,000,000 cUSD | hook trực tiếp `InsufficientLiquidity()` | `SETTLE` trước `SWAP` cũng revert | — | — | Fork có cấp cUSD cho ví; DEX không được cấp vốn |

Mọi token trong bảng đều có **6 decimals** theo `decimals()` tại block 41,274,562. Lượng là số token, **không** quy ra USD. Gas là `debug_traceCall.gasUsed` của toàn Universal Router call, không phải ước tính gas của V4Quoter. Kết quả chi tiết, gồm input balance và output lấy từ lời gọi `transfer` cuối tới payer, ở `tempo_real_route_summary.json`, `tempo_fork_usecases_41183156.jsonl` và `tempo_fork_trace_25m.json`.
Riêng dòng giao dịch một chặng dùng gas của receipt thật và dữ liệu lưu ở `tempo_onehop_control_41183156.json`, `../tempo_replay_4.jsonl`.

## Pool, địa chỉ và giới hạn kiểm kê

- PoolManager `0x33620f62c5b9b2086dd6b62f4a297a9f30347029`; V4Quoter `0x20e6487c371a2086f841ef453f85378223df4f4e`; Universal Router `0x182a927119D56008d921126764bF884221b10f59`, theo [deployment Uniswap v4](https://developers.uniswap.org/docs/protocols/v4/deployments).
- Hook được kiểm tra: `TempoExchangeAggregator v1.0` tại `0x7169a78a59f136876e724b648fbb339a42f46888`, verified bằng `aggregatorHookVersion()`, `tempoExchange()` và `AggregatorPoolRegistered` ở `../tempo_probe_41274562.jsonl`. Không suy rộng sang các deployment hook khác.
- `Initialize` từ PoolManager trong `tempo_pool_inventory_121m_123m.jsonl`: PathUSD `0x20c0000000000000000000000000000000000000` / USDC.e `0x20c000000000000000000000b9537d11c60e8b50`, pool `0x00cdb9b18686cc49430bd3ea24a241633baf4af84029a014f2be22ec5e295588`, block 12,180,656; PathUSD / cUSD `0x20c0000000000000000000000520792dcccccccc`, pool `0x68d0800bf43bbf6ca33f5d92ce22b882c04b12194358b38ce91fa10b55e6ce57`, block 12,180,694; PathUSD / USDT0 `0x20c00000000000000000000014f22ca97301eb73`, pool `0x592553ff97e181f7d1df0d5a63937f5f11ae2d9e0964e22d193313c4506a9e22`, block 12,180,723. Cả ba fee 500, tickSpacing 10, cùng hook.
- Bốn route trong bảng là bốn trong sáu hoán vị token ngoài PathUSD qua hai pool aggregator. **Cả hai chặng đều là pool Uniswap v4 dùng Tempo hook.** Vì vậy chúng xác nhận multi-hop và vị trí hook đầu/cuối, nhưng **không** xác nhận route kết hợp một chặng Tempo với một chặng v4 thường có thanh khoản. Pool no-hook PathUSD/USDC.e `0xce0d1c0b87a8b1a92cd0865013c2bd9440be49fdf7a3d3514e82f02352a4e2dd` (Initialize block 40,113,345) tồn tại nhưng V4Quoter revert ở 1 token tại block 41,274,562; không tính là phương án thay thế thực thi. Pool PathUSD/cbBTC `0x51d5133ef1f7317b98228f02f49a5a828035f2c2081584c553db622faa4c6830` cũng không quote được ở 1 token. Các pool khác ngoài phạm vi log đã quét vẫn có thể tồn tại.
- Phạm vi log có lọc: PathUSD block 12.1–12.3 triệu và 38–41.274562 triệu; cUSD ở 12–15 và 30–41.274562 triệu. Không quét toàn chain. `tempo_pool_inventory_*.jsonl` ghi nguồn gốc. Không tìm thấy direct cUSD/USDT0 trong **những khoảng đã quét**, không chứng minh không tồn tại ở khoảng còn lại hoặc protocol khác.

## Cơ chế và pain point đã đo

1. **Người dùng có cUSD muốn đổi sang USDT0.** Tại block 41,183,156, PM có đúng **19,862,459** đơn vị cUSD. Hook trực tiếp còn quote được 25,000,000 cUSD → 24,995,000 PathUSD → 24,997,499 USDT0. V4Quoter quote đúng đến **19,862,459** cUSD và revert ngay ở **19,862,460**. `tempo_fork_trace_25m.json` ghi hook chặng đầu được gọi, rồi `PoolManager.take(cUSD)` khiến TIP-20 `transfer` revert; không phải revert `QuoteSwap` có chủ đích. Trên fork, `anvil_dealTIP20` đặt **chỉ ví payer** từ 5,249,475 lên 30,000,000 cUSD; PM vẫn 19,862,459, DEX nguyên trạng. Universal Router với thứ tự `SETTLE(cUSD, amount, true)` → `SWAP_EXACT_IN` → `TAKE` thực thi được; output ở 25 cUSD là **24.997499 USDT0**, khớp ghép hai hook quote, gas **571,946**. Đây là ca **mất quote của route có thể thực thi bằng Universal Router thật nếu prepay**. Không phải bằng chứng rằng calldata UniRoute production prepay.
2. **Điều kiện là thứ tự nạp đầu vào, không phải hook bị bỏ qua.** Cùng fork, khi dùng thứ tự lịch sử thường thấy `SWAP` → `SETTLE` → `TAKE`, cả quoter và Universal Router đều revert ở 19,862,460/20,000,000/25,000,000 cUSD: hook gọi `take` trước khi token từ ví vào PM. Dưới ngưỡng, cả hai thành công và output khớp (1 cUSD: 0.999899 USDT0; 19.862459 cUSD: 19.860472 USDT0). Trên RPC thật, bốn route hai chặng ở bảng đều gọi **cả hai hook** và quote khớp output. `tempo_fork_trace_25m.json` có một hook call trước lỗi quote/standard execution và hai hook call trong execution prepay thành công. Vì `uniroute-public` thiếu implementation `methodParameters` và `isTempoAggHook`, chưa chứng minh app có thể tạo prepay calldata hoặc từng đưa route này vào so sánh.
3. **Chưa đo được mất giá tốt sau gas.** Tìm thấy no-hook direct PathUSD/USDC.e nhưng chưa có execution hợp lệ ở amount so sánh. Không có cặp direct cUSD/USDT0 đã xác nhận trong phạm vi này. Vì vậy **lợi ích sau gas và tần suất người dùng thực tế đều chưa biết**. Tỷ lệ lỗi trong amount chủ động quanh ngưỡng không phải tỷ lệ xảy ra production. Nếu ứng dụng chỉ phát hành thứ tự `SWAP` rồi `SETTLE`, thiếu quote ở trên đi kèm giao dịch thất bại; riêng việc sửa quote sẽ chưa tạo ra giao dịch tốt hơn.

Đối chứng lỗi hợp lệ: ở block 41,183,156, direct `hook.quote` cho **1,000,000 cUSD** trả `InsufficientLiquidity()` (`0xbb55fd27`); execution prepay cũng revert ở Tempo Exchange với cùng selector, dù ví test được cấp đủ input (`tempo_fork_trace_illiquid.json`). Điều này tách thiếu thanh khoản bên DEX khỏi ngưỡng số dư PM.

## Mức tin cậy và chạy lại

- **RPC thật, không override:** 4 route trong bảng, cùng block/caller/allowance; output từ trace của Universal Router, cả hai hook được gọi. Các ví lịch sử lấy từ tx `0x8745491a51213e9728db9b6597642cdbd26581f0d85392354e23140cc6f3dae1` và `0xf7a35c2895756f201ab93bfe7dda27345b88f684172f3bb670b47c8d4084bf4a`. Route USDC.e tái dùng Permit2 signature nguyên bản ở parent block.
- **Fork có override ví:** ngưỡng U1/U3 và đối chứng thiếu thanh khoản. Fork giữ implementation hook/PoolManager/DEX/Universal Router thật. `tempo_fork_usecases.py` tự snapshot và revert; chỉ `anvil_dealTIP20` cho payer. Không biến kết quả này thành replay production chưa override.
- **Code:** UniRoute public `AggHookQuoter.ts:31-35` tách nhánh hook quote cho một chặng; `DeepQuoteStrategy.ts:156-252` đưa multi-hop vào quoter chuẩn. `V4Quoter.sol` thực hiện các swap trong `PoolManager.unlock` trước khi revert quote; hook thật gọi `PoolManager.take` trong `beforeSwap`. Universal Router hỗ trợ action `SETTLE` trước `SWAP`, nhưng transaction lịch sử dùng `SWAP` trước `SETTLE`. Thứ tự production UniRoute chưa xác minh.
- Commit: v4-core `46c6834698c48bc4a463a86d8420f4eb1d7f3b75`; v4-periphery `9969eec44cfdf07e24b41de47f40276a58401976`; v4-hooks-public `e4eabe526f9b516fff78d98ba781251747f0fd6e`; uniroute-public `2961efa8d44b80d353ee3af82cf868702bb6ab6a`; universal-router `543e1a19d6e21e31ced2512eec5792b50f13a0ba`.

```bash
cd /Users/harry/uniswap-v4-study/quote-harness
python3 tempo_multihop_replay.py --source cusd --target usdt0 --block 41183156 --amount 1000000 --amount 5249475 --trace
python3 tempo_multihop_replay.py --source usdce --target usdt0 --payer 0x915926b61b61ef91ea00a46cccf6a85c289b32a1 --block 41115563 --amount 1000000 --permit-template-tx 0xf7a35c2895756f201ab93bfe7dda27345b88f684172f3bb670b47c8d4084bf4a --trace
```

Fork (terminal khác cho dòng Anvil; script sau chỉ gọi RPC local):

```bash
/Users/harry/.foundry/bin/anvil --fork-url https://rpc.tempo.xyz --fork-block-number 41183156 --port 8546 --silent
python3 tempo_fork_usecases.py > tempo_fork_usecases_41183156.jsonl
```

**Kết luận quyết định:** có ca thực tế về **cơ chế ngưỡng số dư** và Universal Router thật có thể thực thi khi đổi thứ tự action. Chưa đủ bằng chứng để tuyên bố người dùng UniRoute production đang mất giao dịch tốt: cần xác minh calldata production có prepay hoặc có thể phát hành prepay, tìm phương án cạnh tranh thực thi cùng trạng thái, và đo output sau gas. Nếu production chỉ dùng `SWAP` trước `SETTLE`, use case này chưa chứng minh pain về chất lượng giá; cả quote lẫn giao dịch đều thất bại ở ngưỡng.
