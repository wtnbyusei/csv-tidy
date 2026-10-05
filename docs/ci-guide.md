# CI 導入の手順（GitHub Actions）

開発者が自分で CI を導入し、仕組みを理解するための手順。開発計画（[plan.md](plan.md)）の作業1にあたる。

- 作成日: 2026-10-01
- 用語: 分からない用語は [glossary.md](glossary.md) を参照

## 1. 用語

| 用語 | 説明 |
| --- | --- |
| CI | GitHub に変更を送るたびに、テストなどを自動で実行する仕組み |
| GitHub Actions | GitHub に付いている CI の機能。公開リポジトリでは無料で使える |
| ワークフロー | 「いつ」「何を」実行するかを書いた設定ファイル。`.github/workflows/` に YAML（字下げで構造を表す設定ファイルの書き方）で書く |
| ジョブ | 1台の仮想マシンで行う作業のまとまり |
| ステップ | ジョブの中の1つ1つの命令 |
| ランナー | ジョブを実行する、GitHub が用意した仮想マシン |
| アクション | 公開されている再利用できる部品。`uses:` で使う。例: リポジトリの中身を取得する `actions/checkout` |

## 2. 準備

- 設計のプルリクエスト（#2）がマージされていること。マージ前に始めると、新しいブランチに PR テンプレートが入っていない。

## 3. 手順1: 最小のワークフローを作って動かす

ブラウザだけでできる。

1. GitHub でリポジトリを開き、上部の「Actions」タブを押す。
2. 「set up a workflow yourself」を押す。`.github/workflows/main.yml` の編集画面が開くので、ファイル名を `ci.yml` に変える。
3. 次の内容を貼り付ける。

   ```yaml
   # ワークフローの名前（Actions タブや PR に表示される）
   name: CI

   # いつ実行するか
   on:
     pull_request:          # プルリクエストを作ったとき・更新したとき
     push:
       branches: [main]     # main に取り込まれたとき

   jobs:
     check:                       # ジョブの名前
       runs-on: ubuntu-latest     # GitHub が用意する Linux の仮想マシンで実行する
       steps:
         - name: リポジトリの中身を取得する
           uses: actions/checkout@v4   # 公開されているアクションを使う

         - name: あいさつ
           run: echo "Hello CI"

         - name: docs フォルダの中身を表示する
           run: ls -la docs
   ```

4. 右上の「Commit changes...」を押す。「Create a new branch for this commit and start a pull request」を選び、ブランチ名を `chore/setup-ci` にして「Propose changes」を押す。
5. プルリクエストの作成画面で、PR テンプレートに沿って説明を書き、作成する。
6. プルリクエストの下の方にチェック（CI の実行結果）が表示される。黄色の ● は実行中、緑の ✓ は成功。
7. 「Details」を押すと、ステップごとの実行ログ（記録）が見られる。「あいさつ」のステップに `Hello CI` と表示されていることを確かめる。

## 4. 手順2: わざと失敗させてみる

1. 同じブランチの `ci.yml` で、`run: echo "Hello CI"` を `run: exit 1` に変えてコミットする。`exit 1` は「失敗として終了する」という命令。
2. チェックが赤い ✗ になる。ログで、どのステップが失敗したかを確かめる。
3. 元に戻してコミットし、緑の ✓ に戻ることを確かめる。
4. 問題がなければマージする。

## 5. 実装の準備で追加したもの

実装の準備（plan.md の作業4、`chore/setup-uv`）で、Claude がワークフローを次のように広げた。手順1で作ったジョブ `check` を、テストを実行するジョブ `test` に置き換えている。

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.13"]
    name: test (Python ${{ matrix.python-version }})
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          python-version: ${{ matrix.python-version }}
          enable-cache: true
      - run: uv sync --locked
      - run: uv run pytest --cov --cov-report=term
      - run: uv run coverage report --include='src/csv_tidy/core/*' --fail-under=90
```

| 部分 | 意味 |
| --- | --- |
| `strategy.matrix` | マトリックス（同じジョブを条件を変えて何回か実行する仕組み）。ここでは Python 3.11 と 3.13 の2回実行する。プルリクエストのチェックも「test (Python 3.11)」「test (Python 3.13)」の2つが表示される |
| `fail-fast: false` | 1つの版で失敗しても、もう1つの版を途中で止めない。どの版で失敗したかを両方見られる |
| `${{ matrix.python-version }}` | マトリックスで指定した値を差し込む書き方 |
| `astral-sh/setup-uv@v7` | uv と、指定した版の Python を用意するアクション |
| `enable-cache: true` | ダウンロードしたライブラリを保存し、次回の実行を速くする（キャッシュ） |
| `uv sync --locked` | `uv.lock` に書かれた版のとおりにライブラリを入れる。`pyproject.toml` と `uv.lock` が食い違っていたら失敗する |
| `uv run pytest --cov` | テストを実行し、カバレッジを測る。テストが1つでも失敗すると、このステップが失敗する |
| `coverage report ... --fail-under=90` | コアのカバレッジが 90% 未満なら失敗にする（テスト計画書 4章） |

アクションの版は、追加した時点（2026-10-05）で最新の v7 にした。手順1で使った `actions/checkout@v4` も v7 に上げている。

E2E テストのジョブ `e2e` は、画面を作る作業9（`feat/web-ui`）で追加する。

## 6. 注意

- `actions/checkout@v4` の `@v4` はアクションの版の指定。より新しい版が出ている可能性があるが、v4 で動く。
- ワークフローのファイルは YAML なので、字下げ（半角スペース）がずれると動かない。タブ文字は使えない。
