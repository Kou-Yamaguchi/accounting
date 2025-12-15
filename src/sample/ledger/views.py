from decimal import Decimal
from datetime import date, datetime, timedelta
from calendar import monthrange
from dataclasses import dataclass

from django.shortcuts import render, get_object_or_404
from django.db.models import F, Q, Value, CharField, Prefetch, Sum
from django.views.generic import (
    ListView,
    CreateView,
    UpdateView,
    DeleteView,
    TemplateView,
)
from django.urls import reverse_lazy
from django.db import transaction
from django.core.exceptions import ImproperlyConfigured

from ledger.models import JournalEntry, Account, Debit, Credit, PurchaseDetail
from ledger.forms import JournalEntryForm, DebitFormSet, CreditFormSet
from ledger.services import calculate_monthly_balance, get_fiscal_range
from enums.error_messages import ErrorMessages

@dataclass
class YearMonth:
    year: int
    month: int


@dataclass
class ClosingEntry:
    total_purchase: int
    total_returns: int
    net_purchase: int


@dataclass
class PurchaseItem:
    name: str
    quantity: int
    unit_price: int


@dataclass
class PurchaseBookEntry:
    date: date
    company: str
    items: list[PurchaseItem]
    counter_account: str
    is_return: bool
    total_amount: int


@dataclass
class PurchaseBook:
    date: YearMonth
    book_entries: list[PurchaseBookEntry]  # List of PurchaseBookEntry instances
    closing_entry: ClosingEntry = None
    error: str = None


class AccountCreateView(CreateView):
    model = Account
    fields = ["name", "type"]
    template_name = "ledger/account_form.html"
    success_url = reverse_lazy("account_list")


class AccountListView(ListView):
    model = Account
    template_name = "ledger/account_list.html"
    context_object_name = "accounts"


class AccountUpdateView(UpdateView):
    model = Account
    fields = ["name", "type"]
    template_name = "ledger/account_form.html"
    success_url = reverse_lazy("account_list")


class AccountDeleteView(DeleteView):
    model = Account
    template_name = "ledger/account_confirm_delete.html"
    success_url = reverse_lazy("account_list")


class JournalEntryListView(ListView):
    model = JournalEntry
    template_name = "ledger/journal_entry_list.html"
    context_object_name = "journal_entries"


class JournalEntryFormMixin:
    """
    JournalEntryCreateView / JournalEntryUpdateView の共通処理を切り出すミックスイン。
    - フォームセットの生成（POST の場合はバインド）
    - バリデーション（個別＋借貸合計の一致チェック）
    - トランザクションを使った保存
    """

    debit_formset_class = DebitFormSet
    credit_formset_class = CreditFormSet

    def get_formsets(self, post_data=None, instance=None):
        """
        フォームセットを取得するユーティリティメソッド。
        Args:
            post_data (QueryDict, optional): POSTデータ。デフォルトはNone。
            instance (JournalEntry, optional): JournalEntryインスタンス。デフォルトはNone。
        Returns:
            tuple: (debit_formset, credit_formset)
        """
        if post_data:
            debit_fs = self.debit_formset_class(post_data, instance=instance)
            credit_fs = self.credit_formset_class(post_data, instance=instance)
        else:
            debit_fs = self.debit_formset_class(instance=instance)
            credit_fs = self.credit_formset_class(instance=instance)
        return debit_fs, credit_fs

    def get_context_data(self, **kwargs):
        """
        コンテキストデータにフォームセットを追加する。
        """
        data = super().get_context_data(**kwargs)
        instance = getattr(self, "object", None) or JournalEntry()
        post = self.request.POST if self.request.method == "POST" else None
        debit_fs, credit_fs = self.get_formsets(post, instance)
        data["debit_formset"] = debit_fs
        data["credit_formset"] = credit_fs
        return data

    def form_valid(self, form):
        """
        親フォームは commit=False でインスタンスを作成し、フォームセットを先に検証。
        検証OKならトランザクション内で保存。
        """
        context = self.get_context_data()
        instance = form.save(commit=False)
        debit_formset = context.get("debit_formset")
        credit_formset = context.get("credit_formset")

        # フォームセットのバリデーション
        if not (debit_formset.is_valid() and credit_formset.is_valid()):
            return self.form_invalid(form)

        # 借方・貸方合計チェック（フォームセット内で合計を保持している前提）
        total_debit = getattr(debit_formset, "total_amount", Decimal("0.00"))
        total_credit = getattr(credit_formset, "total_amount", Decimal("0.00"))
        if total_debit != total_credit:
            form.add_error(None, ErrorMessages.MESSAGE_0001.value)
            return self.form_invalid(form)

        # トランザクション内で親子を保存
        with transaction.atomic():
            self.object = instance
            self.object.save()
            debit_formset.instance = self.object
            credit_formset.instance = self.object
            debit_formset.save()
            credit_formset.save()

        return super().form_valid(form)


class JournalEntryCreateView(JournalEntryFormMixin, CreateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "ledger/journal_entry_form.html"
    success_url = reverse_lazy("journal_entry_list")


class JournalEntryUpdateView(JournalEntryFormMixin, UpdateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "ledger/journal_entry_form.html"
    success_url = reverse_lazy("journal_entry_list")


class JournalEntryDeleteView(DeleteView):
    model = JournalEntry
    template_name = "ledger/journal_entry_confirm_delete.html"
    success_url = reverse_lazy("journal_entry_list")


class LedgerSelectView(TemplateView):
    """帳票選択ビュー"""
    template_name = "ledger/ledger_select.html"


class GeneralLedgerView(TemplateView):
    """
    特定の勘定科目の総勘定元帳を取得・表示するビュー。
    URL: /ledger/<str:account_name>/
    """

    template_name = "ledger/general_ledger_partial.html"  # 使用するテンプレートファイル名

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # URLから勘定科目名を取得
        account_name = self.kwargs["account_name"]

        # 1. 勘定科目オブジェクトを取得（存在しない場合は404）
        account = get_object_or_404(Account, name=account_name)
        context["account"] = account
        target_account_id = account.id

        # 取得した勘定科目に関連する取引の科目の種類を全て取得
        # N+1問題を避けるため、prefetch_relatedを使用して関連オブジェクトを事前に取得
        journal_entries = (
            JournalEntry.objects.filter(
                Q(debits__account=account) | Q(credits__account=account)
            )
            .distinct()
            .order_by("date", "pk")
            .prefetch_related(
                Prefetch(
                    "debits",
                    queryset=Debit.objects.select_related("account"),
                    to_attr="prefetched_debits",
                ),
                Prefetch(
                    "credits",
                    queryset=Credit.objects.select_related("account"),
                    to_attr="prefetched_credits",
                ),
            )
        )

        ledger_entries = []
        running_balance = Decimal("0.00")

        for je in journal_entries:
            # 取引に含まれるすべての勘定科目（Accountオブジェクト）を収集
            all_debits = set()
            all_credits = set()

            # プリフェッチされたリレーションを利用して勘定科目を収集
            all_debits = set(debit.account for debit in je.prefetched_debits)
            all_credits = set(credit.account for credit in je.prefetched_credits)

            # 当該勘定科目に関連する明細行を特定
            is_debit_entry = target_account_id in {acc.id for acc in all_debits}

            # ターゲット勘定科目を除外した、相手勘定科目のリスト
            if is_debit_entry:
                other_accounts = all_credits
            else:
                other_accounts = all_debits

            # 3. 相手勘定科目の決定ロジック (単一 vs 諸口)
            counter_party_name = ""
            if len(other_accounts) == 1:
                # 相手勘定科目が1つの場合、その名前をセット
                counter_party_name = [acc.name for acc in other_accounts][0]
            elif len(other_accounts) > 1:
                # 相手勘定科目が複数の場合
                counter_party_name = "諸口"
            else:
                # 相手勘定科目が0の場合（例：自己取引、またはデータ不備）
                counter_party_name = "取引エラー"

            # 明細タイプによって借方・貸方金額を決定

            if is_debit_entry:
                debit_amount = je.prefetched_debits[0].amount
                credit_amount = Decimal("0.00")
                running_balance += debit_amount
            else:
                debit_amount = Decimal("0.00")
                credit_amount = je.prefetched_credits[0].amount
                running_balance -= credit_amount

            entry = {
                "date": je.date,
                "summary": je.summary,
                "counter_party": counter_party_name,
                "debit_amount": debit_amount,
                "credit_amount": credit_amount,
                "running_balance": running_balance,
            }
            ledger_entries.append(entry)

        context["ledger_entries"] = ledger_entries

        return context


class TrialBalanceView(TemplateView):
    """
    試算表ビュー
    該当年度の試算表を表示する。
    URL: /ledger/trial_balance_by_year/
    """
    template_name = "ledger/trial_balance_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year = int(self.request.GET.get("year"))

        start_date, end_date = get_fiscal_range(year)

        # 全勘定科目を取得
        accounts = Account.objects.all().order_by("type", "name")

        trial_balance_data = []

        for account in accounts:
            # 各勘定科目の借方・貸方合計を計算

            debit_total = (
                Debit.objects.filter(
                    account=account,
                    journal_entry__date__gte=start_date,
                    journal_entry__date__lte=end_date,
                )
                .aggregate(Sum('amount'))['amount__sum'] or Decimal("0.00")
            )
            credit_total = (
                Credit.objects.filter(
                    account=account,
                    journal_entry__date__gte=start_date,
                    journal_entry__date__lte=end_date,
                )
                .aggregate(Sum('amount'))['amount__sum'] or Decimal("0.00")
            )

            if account.type == 'asset' or account.type == 'expense':
                total = debit_total - credit_total
            else:
                total = credit_total - debit_total

            trial_balance_data.append({
                "account": account,
                "type": account.type,
                "total": total,
            })

        print(trial_balance_data)

        context["year"] = year
        context["trial_balance_data"] = trial_balance_data

        return context


class BalanceSheetView(TemplateView):
    """貸借対照表ビュー"""
    template_name = "ledger/balance_sheet.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 貸借対照表のデータ取得ロジックをここに実装
        year = int(self.request.GET.get("year", datetime.now().year))
        context["year"] = year
        start_date, end_date = get_fiscal_range(year)

        for account_type in ['asset', 'liability', 'equity']:
            accounts = Account.objects.filter(type=account_type).order_by("name")
            account_data = []

            for account in accounts:
                debit_total = (
                    Debit.objects.filter(
                        account=account,
                        journal_entry__date__gte=start_date,
                        journal_entry__date__lte=end_date,
                    )
                    .aggregate(Sum('amount'))['amount__sum'] or Decimal("0.00")
                )
                credit_total = (
                    Credit.objects.filter(
                        account=account,
                        journal_entry__date__gte=start_date,
                        journal_entry__date__lte=end_date,
                    )
                    .aggregate(Sum('amount'))['amount__sum'] or Decimal("0.00")
                )

                if account_type == 'asset':
                    balance = debit_total - credit_total
                else:
                    balance = credit_total - debit_total

                account_data.append({
                    "account": account,
                    "type": account_type,
                    "balance": balance,
                })

            context[f"{account_type}_accounts"] = account_data
        return context


class AbstractCashBookView(TemplateView):
    """
    出納帳の共通処理を提供する抽象ビュー。
    サブクラスは TARGET_ACCOUNT_NAME を設定するだけで利用可能。
    戻り値のコンテキスト:
      - book_data: [{ "date", "summary", "income", "expense", "balance" }, ...]
      - account_name, current_month, next_month_carryover, error_message (必要時)
    """

    template_name = "ledger/cash_book.html"
    TARGET_ACCOUNT_NAME = None  # サブクラスで設定すること

    def _parse_year_month(self):
        try:
            year = int(self.kwargs.get("year", datetime.now().year))
            month = int(self.kwargs.get("month", datetime.now().month))
        except (ValueError, TypeError):
            now = datetime.now()
            year, month = now.year, now.month
        return year, month

    def get_context_data(self, **kwargs):
        if not self.TARGET_ACCOUNT_NAME:
            raise ImproperlyConfigured(
                ErrorMessages.MESSAGE_0002.value
            )

        context = super().get_context_data(**kwargs)
        year, month = self._parse_year_month()

        # サービスに処理を委譲（サービスはdictで data/ending_balance または error を返す想定）
        result = calculate_monthly_balance(self.TARGET_ACCOUNT_NAME, year, month)

        if "error" in result:
            context["error_message"] = result["error"]
            context["book_data"] = []
            context["next_month_carryover"] = None
        else:
            # services.calculate_monthly_balance の返却スキーマに合わせて取り出す
            context["book_data"] = result.get("data", [])
            context["next_month_carryover"] = result.get("ending_balance")

        context["account_name"] = self.TARGET_ACCOUNT_NAME
        context["current_month"] = datetime(year, month, 1)
        return context


class CashBookView(AbstractCashBookView):
    """現金出納帳"""

    TARGET_ACCOUNT_NAME = "現金"


class CurrentAccountCashBookView(AbstractCashBookView):
    """当座預金出納帳"""

    TARGET_ACCOUNT_NAME = "当座預金"


class PettyCashBookView(AbstractCashBookView):
    """小口現金出納帳"""

    TARGET_ACCOUNT_NAME = "小口現金"


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
