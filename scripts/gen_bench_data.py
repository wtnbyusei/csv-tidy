"""性能測定（NFR-01、テスト計画書 8 章）に使う、約 10MB の CSV を作る。

    uv run python scripts/gen_bench_data.py                 # tests/perf/data/bench_10mb.csv を作る
    uv run python scripts/gen_bench_data.py --out x.csv --size 5000000

10 列の顧客データのような CSV（約 10 万行）を、上限（10,485,760 バイト）を超えない大きさまで書く。
整形で変更が起きるように、一定の割合で次の行を混ぜる。乱数の種を固定しているので、
何回作っても同じ中身になる。

- 前後に空白のあるセル（20 行に 1 行）
- 空行（50 行に 1 行）
- 前の行と同じ行（100 行に 1 行）
"""

import argparse
import random
from pathlib import Path

# アップロードできる上限（core/models.py の MAX_BYTES と同じ）
MAX_BYTES = 10 * 1024 * 1024

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tests" / "perf" / "data" / "bench_10mb.csv"
# 上限より少し小さくする（上限を超えると 413 になり、測定にならない）
DEFAULT_SIZE = MAX_BYTES - 64 * 1024

HEADER = ["顧客番号", "氏名", "フリガナ", "年齢", "都道府県", "住所", "電話番号", "メール", "会社名", "登録日"]
FAMILY = ["山田", "佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "中村", "小林", "加藤"]
GIVEN = ["太郎", "花子", "一郎", "次郎", "美咲", "健太", "陽菜", "翔", "結衣", "大輔"]
KANA = ["ヤマダ", "サトウ", "スズキ", "タカハシ", "タナカ", "イトウ", "ワタナベ", "ナカムラ", "コバヤシ", "カトウ"]
PREFS = ["東京都", "大阪府", "愛知県", "福岡県", "北海道", "京都府", "神奈川県", "広島県", "宮城県", "沖縄県"]


def make_row(rng: random.Random, number: int) -> list[str]:
    family = rng.randrange(len(FAMILY))
    return [
        f"C{number:07d}",
        f"{FAMILY[family]}{GIVEN[rng.randrange(len(GIVEN))]}",
        KANA[family],
        str(rng.randint(18, 90)),
        PREFS[rng.randrange(len(PREFS))],
        f"{rng.randint(1, 9)}-{rng.randint(1, 30)}-{rng.randint(1, 20)}",
        f"0{rng.randint(10, 99)}-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}",
        f"u{number}@ex.jp",
        f"サンプル{rng.randint(1, 500)}",
        f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
    ]


def generate(size: int, seed: int = 1) -> bytes:
    """size バイトを超えない範囲で、できるだけ大きな CSV（UTF-8、LF）を作る。"""
    rng = random.Random(seed)
    lines = [",".join(HEADER)]
    total = len(lines[0].encode()) + 1
    previous: list[str] = []
    number = 0
    while True:
        number += 1
        if number % 50 == 0:
            line = ""  # 空行
        elif number % 100 == 1 and previous:
            line = ",".join(previous)  # 前の行と同じ行
        else:
            row = make_row(rng, number)
            if number % 20 == 0:
                row[1] = f"  {row[1]}　"  # 前後の空白
            previous = row
            line = ",".join(row)
        length = len(line.encode()) + 1
        if total + length > size:
            break
        lines.append(line)
        total += length
    return ("\n".join(lines) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="書き出すファイル")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE, help=f"大きさの上限（バイト。{MAX_BYTES:,} 以下）")
    args = parser.parse_args()
    if args.size > MAX_BYTES:
        parser.error(f"--size は {MAX_BYTES:,} 以下にしてください")
    data = generate(args.size)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(data)
    rows = data.count(b"\n") - 1
    print(f"{args.out}: {len(data):,} バイト、{rows:,} 行（ヘッダーを除く）")


if __name__ == "__main__":
    main()
