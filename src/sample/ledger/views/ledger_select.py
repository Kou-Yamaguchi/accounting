from django.views.generic import ListView


class LedgerSelectView(ListView):
    template_name = "ledger/ledger_select.html"
    context_object_name = "reports"

    reports = [
        {
            "title": "仕訳帳",
            "description": "日付順にすべての仕訳を表示",
            "icon": "bi-journal-bookmark",
            "url_name": "journal_entry_list",
            "enabled": True,
        },
        {
            "title": "総勘定元帳",
            "description": "すべての仕訳を時系列で確認できます",
            "icon": "bi-journal-text",
            "url_name": "general_ledger",
            "enabled": True,
        },
        {
            "title": "試算表",
            "description": "各勘定の残高を一覧表示",
            "icon": "bi-table",
            "url_name": "trial_balance",
            "enabled": True,
        },
        {
            "title": "貸借対照表",
            "description": "資産・負債・純資産の状態を表示",
            "icon": "bi-bar-chart",
            "url_name": "balance_sheet",
            "enabled": True,
        },
        {
            "title": "損益計算書",
            "description": "収益と費用から利益を確認",
            "icon": "bi-graph-up",
            "url_name": "profit_and_loss",
            "enabled": True,
        },
        {
            "title": "現金出納帳",
            "description": "現金の入出金を管理",
            "icon": "bi-wallet2",
            "url_name": "cash_book",
            "enabled": False,
        },
        {
            "title": "当座預金出納帳",
            "description": "当座預金の入出金を管理",
            "icon": "bi-bank",
            "url_name": "current_account_cash_book",
            "enabled": False,
        },
        {
            "title": "小口現金出納帳",
            "description": "小口現金の入出金を管理",
            "icon": "bi-cash-coin",
            "url_name": "petty_cash_book",
            "enabled": False,  # 将来的に実装予定
        },
        {
            "title": "固定資産台帳",
            "description": "固定資産の取得・減価償却を管理",
            "icon": "bi-building",
            "url_name": "fixed_asset_ledger",
            "enabled": False,  # 将来的に実装予定
        },
        {
            "title": "売上帳",
            "description": "売上の記録を管理",
            "icon": "bi-receipt",
            "url_name": "sales_ledger",
            "enabled": False,  # 将来的に実装予定
        },
        {
            "title": "仕入帳",
            "description": "仕入の記録を管理",
            "icon": "bi-basket3",
            "url_name": "purchase_ledger",
            "enabled": False,  # 将来的に実装予定
        },
        {
            "title": "売掛金元帳",
            "description": "売掛金の管理",
            "icon": "bi-people",
            "url_name": "accounts_receivable_ledger",
            "enabled": False,  # 将来的に実装予定
        },
        {
            "title": "買掛金元帳",
            "description": "買掛金の管理",
            "icon": "bi-truck",
            "url_name": "accounts_payable_ledger",
            "enabled": False,  # 将来的に実装予定
        },
    ]

    def get_queryset(self):
        return self.reports
