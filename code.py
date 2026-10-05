def calculate_average(data_list):
    """リストの要素の平均値を計算します。"""
    if not data_list:
        return 0  # リストが空の場合は平均値は0とします
    return sum(data_list) / len(data_list)

def read_data_from_csv(filename="data.csv"):
    """カンマ区切りのCSVファイルから数値を読み取り、リストとして返します。
    ファイル内の各行をカンマで分割し、数値に変換します。"""
    data_list = []
    try:
        with open(filename, 'r') as file:
            for line in file:
                # 行末の改行や空白を取り除く
                line = line.strip()
                if not line:
                    continue  # 空行はスキップ

                # カンマで分割し、それぞれの部分を数値に変換を試みる
                parts = [part.strip() for part in line.split(',') if part.strip()]
                
                for part in parts:
                    try:
                        number = float(part)
                        data_list.append(number)
                    except ValueError:
                        # 数値に変換できない場合はスキップし、警告を出す
                        print(f"警告: 無効な数値データが見つかりました (行: '{line}', 値: {part})。この値はスキップされました。")
                        continue
        return data_list
    except FileNotFoundError:
        print(f"エラー: ファイル '{filename}' が見つかりません。")
        return None

# メイン処理の実行
if __name__ == "__main__":
    # 1. ファイルからデータを読み込む
    my_list = read_data_from_csv("data.csv")

    if my_list is not None:
        # 2. 平均値を計算する
        average = calculate_average(my_list)
        # 3. 結果を出力する
        print("-" * 30)
        print(f"読み込まれたデータポイント数: {len(my_list)}")
        print(f"計算された平均値: {average}")
        print("-" * 30)