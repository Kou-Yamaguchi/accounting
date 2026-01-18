from datetime import datetime
from django.db.models import Prefetch, Q
from django.views.generic import TemplateView

from ledger.structures import (
    YearMonth,
    PurchaseBook,
    PurchaseBookEntry,
    PurchaseItem,
    ClosingEntry,
)
from ledger.models import Account, JournalEntry, Debit, Credit, PurchaseDetail
# TODO: 分割時に有効化
# from ledger.models.purchase import PurchaseDetail


class PurchaseBookView(TemplateView):
    """仕入帳ビュー"""

    template_name = "ledger/purchase_book.html"

    def _parse_year_month(self):
        try:
            year = int(self.kwargs.get("year", datetime.now().year))
            month = int(self.kwargs.get("month", datetime.now().month))
        except (ValueError, TypeError):
            now = datetime.now()
            year, month = now.year, now.month
        return YearMonth(year=year, month=month)

    def get_context_data(self, **kwargs):
        """仕入帳データを取得してコンテキストに追加する。

        Args:
            year (int): 対象年
            month (int): 対象月

        Returns:
            PurchaseBook: 仕入帳データのコンテキスト
        """
        context = super().get_context_data(**kwargs)
        target_year_month = self._parse_year_month()

        # 勘定科目「仕入」のIDを取得（事前にAccountテーブルに「仕入」を登録しておく）
        try:
            purchase_account = Account.objects.get(name="仕入")
        except Account.DoesNotExist:
            context["error"] = "勘定科目「仕入」が見つかりません。"
            return context

        # 1. JournalEntryの取得とprefetch_related
        # 勘定科目の片方が「仕入」となっている取引を抽出
        # 仕入は費用なので、増加（純仕入）は借方（Debit）、減少（仕入戻し・値引）は貸方（Credit）

        # Prefetchオブジェクトを使用して、関連データを効率的に取得
        credit_prefetch = Prefetch(
            "credits",
            queryset=Credit.objects.select_related("account"),
            to_attr="prefetched_credits",
        )
        debit_prefetch = Prefetch(
            "debits",
            queryset=Debit.objects.select_related("account"),
            to_attr="prefetched_debits",
        )
        # purchase_prefetch = Prefetch(
        #     "purchase_details",
        #     queryset=PurchaseDetail.objects.select_related("item"),
        #     to_attr="prefetched_purchase_details",
        # )

        # 「仕入」勘定を含む取引、かつ対象年月内の取引をフィルタリング
        # Qオブジェクトを使ってOR検索 (仕入が借方 OR 仕入が貸方)
        purchase_journals = (
            JournalEntry.objects.filter(
                Q(debits__account=purchase_account)
                | Q(credits__account=purchase_account),
                date__year=target_year_month.year,
                date__month=target_year_month.month,
            )
            .prefetch_related(
                credit_prefetch,
                debit_prefetch,
                "purchase_details",
                "company",  # 取引先情報も取得
            )
            .order_by("date")
        )

        # 5. 整形済みリストの作成と 6. 合計の計算
        book_entries: list[PurchaseBookEntry] = []
        total_purchase = 0  # 総仕入高
        total_returns_allowances = 0  # 仕入値引戻し高 (純額で計算)

        # 仕入戻し/値引の勘定科目を定義 (日商簿記3級では「仕入」勘定を直接減らす処理が多いですが、
        # 仕訳の**相手勘定**の名称として仕訳摘要を生成するため、今回は借方の相手科目が純仕入、貸方の相手科目が戻し/値引と判断します。
        # または、仕入戻し等の場合はCredit/Debitテーブルの相手勘定を判断します)

        for entry in purchase_journals:
            # 仕入の取引金額と、仕入の相手勘定を特定
            is_purchase_increase = any(
                d.account_id == purchase_account.id for d in entry.prefetched_debits
            )
            is_purchase_decrease = any(
                c.account_id == purchase_account.id for c in entry.prefetched_credits
            )

            # 仕入の増減と金額の特定
            if is_purchase_increase:
                # 純仕入 (仕入が借方)
                amount = sum(
                    d.amount
                    for d in entry.prefetched_debits
                    if d.account_id == purchase_account.id
                )
                # 仕入の相手勘定（貸方）を特定。ここでは買掛金など1つに絞れる前提
                counter_entry = next((c for c in entry.prefetched_credits), None)
                transaction_type = "仕入"
                total_purchase += amount
            elif is_purchase_decrease:
                # 仕入戻し・値引 (仕入が貸方)
                amount = sum(
                    c.amount
                    for c in entry.prefetched_credits
                    if c.account_id == purchase_account.id
                )
                # 仕入の相手勘定（借方）を特定。ここでは買掛金など1つに絞れる前提
                counter_entry = next((d for d in entry.prefetched_debits), None)
                transaction_type = "仕入引戻し"
                total_returns_allowances += amount  # 戻し・値引として加算
            else:
                continue  # 万一「仕入」がない場合はスキップ

            counter_account_name = (
                counter_entry.account.name if counter_entry else "不明"
            )
            company_name = entry.company.name if entry.company else "不明"

            # 2. 取引ごとの摘要文字列を生成 & 3. 内訳フィールドの計算
            total_detail_amount = 0

            # 1行目: 会社名と相手勘定
            # 摘要の1行目は会社名と「掛」「掛戻し」など
            abstract_line1 = f"{company_name} "
            if transaction_type == "仕入":
                # 買掛金/現金など
                if counter_account_name == "買掛金":
                    abstract_line1 += "掛"
                elif counter_account_name == "現金":
                    abstract_line1 += "現金払"
                # その他、相手勘定名で表現
                else:
                    abstract_line1 += f"（{counter_account_name}）"
            elif transaction_type == "仕入引戻し":
                if counter_account_name == "買掛金":
                    abstract_line1 += "掛戻し"
                else:
                    abstract_line1 += f"（{counter_account_name}戻）"

            # 内訳明細の作成
            # 項目は空白で初期化
            purchase_detail = PurchaseBookEntry(
                date=entry.date,
                company=company_name,
                items=[],
                counter_account=counter_account_name,
                is_return=(transaction_type == "仕入引戻し"),
                total_amount=amount,
            )

            # 商品の数だけ内訳行を追加
            for detail in entry.purchase_details.all():
                item_name = detail.item.name if detail.item else "不明商品"
                detail_amount = detail.quantity * detail.unit_price

                purchase_item = PurchaseItem(
                    name=item_name,
                    quantity=detail.quantity,
                    unit_price=detail.unit_price,
                )

                purchase_detail.items.append(purchase_item)

                total_detail_amount += detail_amount

            # 4. 金額の確認 (仕訳金額と内訳の合計が一致することを確認)
            if round(total_detail_amount) != round(amount):
                # 会計上のエラーなのでログ出力などが望ましいが、今回はデータ表示を優先
                print(
                    f"Warning: Journal ID {entry.id} - Detail total ({total_detail_amount}) does not match entry amount ({amount})."
                )
                context["error"] = (
                    f"仕訳ID {entry.id} の内訳金額合計が仕訳金額と一致しません。"
                )

            # 整形データの作成
            book_entries.append(purchase_detail)

        # 6. 純仕入高の計算
        net_purchase = total_purchase - total_returns_allowances

        purchase_book = PurchaseBook(
            date=target_year_month,
            book_entries=book_entries,
            closing_entry=ClosingEntry(
                total_purchase=total_purchase,
                total_returns=total_returns_allowances,
                net_purchase=net_purchase,
            ),
        )

        # テンプレートに渡すコンテキストに追加
        context["purchase_book"] = purchase_book

        return context
