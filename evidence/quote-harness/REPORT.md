# Kiểm thử báo giá EXACT_IN Uniswap v4

Phần tiếp theo dùng pool và Universal Router thật trên Tempo, gồm ngưỡng số dư và giới hạn bằng chứng production: [REAL_TEMPO_REPORT.md](REAL_TEMPO_REPORT.md).

Ngày kiểm tra: 2026-09-26. Không gửi giao dịch thật. `results.txt` là lần chạy cuối: **13/13 test PASS**; PASS nghĩa là kỳ vọng của test được xác nhận, kể cả ca cố ý tái hiện lỗi quote.

## Repo và công cụ

| Repo | Đường dẫn tuyệt đối | Commit |
|---|---|---|
| v4-core | `/Users/harry/uniswap-v4-study/v4-core` | `46c6834698c48bc4a463a86d8420f4eb1d7f3b75` |
| v4-periphery | `/Users/harry/uniswap-v4-study/v4-periphery` | `9969eec44cfdf07e24b41de47f40276a58401976` |
| v4-hooks-public | `/Users/harry/uniswap-v4-study/v4-hooks-public` | `e4eabe526f9b516fff78d98ba781251747f0fd6e` |
| uniroute-public | `/Users/harry/uniswap-v4-study/uniroute-public` | `2961efa8d44b80d353ee3af82cf868702bb6ab6a` |
| universal-router | `/Users/harry/uniswap-v4-study/universal-router` | `543e1a19d6e21e31ced2512eec5792b50f13a0ba` |

Foundry v1.8.3, solc 0.8.26 (PoolManager) và 0.8.29 (harness/hook) đã cài. `v4-hooks-public` có các submodule cần thiết. Harness nhập `V4Quoter.sol` từ submodule được pin; file này giống hệt file trong repo `v4-periphery` ở commit trên (`cmp`). PoolManager build từ repo `v4-core`; `PoolManager.sol` và `IPoolManager.sol` giống hệt bản submodule của `v4-hooks-public`.

## Fixture và phương pháp

- A/B/C là `MockTIP20` 6 decimals. Caller `alice` có 10^12 đơn vị mỗi token và approve router. Đường no-hook/hook phí có liquidity 10^9 trong range tick ±600, LP fee 0, giá khởi tạo 1:1. Pool B/C gửi khoảng 29.55 triệu B vào PoolManager. Giao dịch chuẩn dùng input 1,000,000 đơn vị (1 token).
- `FixedOutputFeeHook` thực thi luật độc lập: nhận 100 đơn vị **output** từ PoolManager trong `afterSwap`, yêu cầu `hookData=0x42`. Bật/tắt phí trên cùng snapshot, rồi so output và số token hook thật nhận. H1/H2 là hai instance khác nhau.
- `TempoExchangeAggregator.sol` là implementation thật của `v4-hooks-public`; chỉ `MockTempoExchange` thay precompile bên ngoài. Mock exchange có phí 0.1%, được cấp 10^12 A/B. PoolManager **không** được cấp sẵn A trong G và H-first. H-last có A từ LP của pool C/A. Test `explicit_manager_seed_diagnostic` là ngoại lệ có tên rõ: mint 1,000,000 A vào PoolManager trước **cả quote lẫn execution**.
- Quote dùng `V4Quoter.quoteExactInput` (trừ G dùng thêm `hook.quote` trực tiếp), cùng caller và state ban đầu với một lần gọi `ExactInPathRouter.swapExactIn`. Router chẩn đoán mở **một** `PoolManager.unlock`, nạp input từ alice trước, gọi mọi `PoolManager.swap` trong cùng transaction, rồi lấy output cuối. Nó không phải calldata production của UniRoute/Universal Router. Gas dưới đây là gas toàn lời gọi router chẩn đoán, không phải gas Universal Router production.
- `alice` là EOA caller của cả hai lời gọi, nhưng tham số `sender` mà hook nhận từ PoolManager là địa chỉ **V4Quoter** ở nhánh quote và **ExactInPathRouter** ở nhánh thực thi. Hai hook của fixture không phụ thuộc `sender`; hook kiểm soát quyền theo router/caller cần phép kiểm chứng riêng.

## Kết quả

Mọi output đều là đơn vị nhỏ nhất của token C/B. Cột “quote → execution” là của **cùng route**; dấu `—` là quoter chuẩn revert. Gas là lần bật phí nếu có.

| Ca | Quote → execution | Gas router | Kết luận |
|---|---:|---:|---|
| A: A→B no-hook | 999000 → 999000 | 111641 | PASS đối chứng một chặng |
| B: A→B→C no-hook | 998002 → 998002 | 143961 | PASS đối chứng nhiều chặng |
| C: A→B H1, phí tắt/bật | 999000→999000 / 998900→998900 | 191753 | PASS; hook thật nhận 100 B |
| D: A→B H1→C, phí tắt/bật | 998002→998002 / 997903→997903 | 231374 | PASS; H1 ở chặng đầu được gọi và nhận 100 B |
| E: C→A→B H1, phí tắt/bật | 998002→998002 / 997902→997902 | 229402 | PASS; H1 ở chặng cuối được gọi và nhận 100 B |
| F: A→B H1→C H2, cả hai phí tắt/bật | 998002→998002 / 997803→997803 | 311488 | PASS; H1 nhận 100 B, H2 nhận 100 C |
| G: A→B Tempo | V4Quoter `—`; `hook.quote` 999000 → 999000 | 230464 | **Tái hiện quote mất** nếu dùng quoter chuẩn; nhánh trực tiếp đúng trong fixture |
| H-first: A→B Tempo→C | V4Quoter `—`; ứng viên ghép 998002 → 998002 | 252984 | **Tái hiện quote mất dù giao dịch đầy đủ chạy**; ghép quote chỉ là chẩn đoán đã được đối chiếu |
| H-last: C→A→B Tempo | 998001 → 998001 | 258312 | PASS; quoter chuẩn hoạt động vì PoolManager có 29,553,011 A từ LP C/A |
| H-first, cấp A rõ ràng cho PoolManager | 998002 → 998002 | 235884 | PASS chẩn đoán điều kiện số dư; cấp 1,000,000 A bằng `MockTIP20.mint` trước cả hai nhánh |
| H-first, không cấp A, input 1,000 / 1m / 10m / 25m | V4Quoter đều `—`; execution 998 / 998002 / 9891187 / 24366447 | 252884 / 403784 / 416793 / 417192 | PASS tái hiện nhiều mức; 25m gần số dư B của pool B/C |
| Hook data sai `0x` | Cả hai revert `WrongHookData` | — | PASS: hook được gọi và điều kiện dữ liệu có hiệu lực |
| No-hook thật sự thiếu thanh khoản, input 10^12 | Quote `NotEnoughLiquidity`; execution `PartialFill(30452989,10^12)` | — | PASS đối chứng lỗi hợp lệ, không phải quote bị bỏ sót |

## Trace và cơ chế

`trace_F.txt` ghi cả H1 và H2 `afterSwap(...,0x42)` **trong V4Quoter**, sau đó revert `QuoteSwap(997803)` có chủ đích; trong lần router chạy, hai callback xuất hiện lại và token phí chuyển thật. Vì vậy giả thuyết “multi-hop bỏ qua luật custom hook” bị bác bỏ cho đường v4 chuẩn này.

`trace_H_first.txt` ghi `V4Quoter.quoteExactInput` → `PoolManager.swap` → `TempoExchangeAggregator.beforeSwap` → `PoolManager.take(A, hook, 1,000,000)` → token A `transfer` revert vì PoolManager có 0 A. Đây là **revert thật**, không phải `QuoteSwap`. Cùng snapshot, router nạp A từ alice trước khi swap; hook được gọi, exchange mock đổi 1,000,000 A thành 999,000 B, pool B/C cho 998,002 C. `trace_H_last.txt` cho thấy hook ở chặng cuối cũng được gọi; quoter hoạt động vì LP C/A đã nạp A vào PoolManager. `trace_illiquid.txt` phân biệt rõ lỗi thiếu thanh khoản thật. `trace_wrong_data.txt` ghi `WrongHookData` ở cả quote và execution.

UniRoute source tại commit đã ghi: `AggHookQuoter.ts:31-35` chỉ tách **single-hop** thỏa `isTempoAggHook`; `DeepQuoteStrategy.ts:156-252` gửi multi-hop sang quote fetcher chuẩn. Điều này đặt H-first vào đúng loại cơ chế nghi vấn **nếu** hook được nhận diện và pool được đưa vào routing. Tuy nhiên bản `uniroute-public` không có `package.json`, `src/lib/helpers.ts` (chứa `isTempoAggHook`), `src/lib/methodParameters.ts` và `src/models`. Vì vậy không thể chạy nguyên service, kiểm chứng tập hook production, hoặc khẳng định H-first đã từng vào danh sách route so sánh. Không có ca “quote đúng nhưng bị loại khỏi bước so sánh” được chứng minh bằng test này.

## Chạy lại

```bash
cd /Users/harry/uniswap-v4-study/quote-harness
FORGE_BIN=/Users/harry/.foundry/bin/forge ./run.sh
/Users/harry/.foundry/bin/forge test --offline --match-test test_H_tempo_first_quoter_fails_but_router_succeeds -vvvv
```

Trước lệnh trace, `v4-core/out/PoolManager.sol/PoolManager.json` phải tồn tại; `run.sh` build artifact này. Các log `results.txt`, `trace_F.txt`, `trace_G.txt`, `trace_H_first.txt`, `trace_H_last.txt`, `trace_illiquid.txt`, `trace_wrong_data.txt` nằm trong thư mục này.

Kiểm chứng bổ sung trên Tempo chain 4217 đã được lưu ở `../tempo_rpc_probe.py`, `../tempo_probe_41274562.jsonl` và `../tempo_replay_4.jsonl`: tại block 41,274,562, 4 giao dịch EXACT_IN một chặng qua deployment `0x7169a78a59f136876e724b648fbb339a42f46888` replay bằng `eth_call` với caller/calldata gốc, 4/4 thành công và output khớp direct hook quote. Không có phép đo multi-hop production từ dữ liệu này; không suy tần suất lỗi ngoài thực tế từ fixture chủ động.
