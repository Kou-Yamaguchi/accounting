# 決算整理仕訳機能 設計提案

## 1. テーブル設計

### 1.1 会計期間モデル (FiscalPeriod)

```python
class FiscalPeriod(models.Model):
    """会計期間を管理するモデル"""
    name = models.CharField(max_length=100)  # 例: "2025年度"
    start_date = models.DateField()  # 期首日: 2025-04-01
    end_date = models.DateField()    # 期末日: 2026-03-31
    is_closed = models.BooleanField(default=False)  # 決算確定フラグ
    company = models.ForeignKey(Company, on_delete=models.CASCADE)

    class Meta:
        unique_together = [['company', 'start_date']]
```

**理由**:

- 決算整理仕訳は特定の会計期間に紐づく
- 期間をまたいだ仕訳の入力制御が可能
- 過去期間の修正防止（is_closedフラグ）

### 1.2 JournalEntryモデルの拡張

```python
ENTRY_TYPE_CHOICES = [
    ('normal', '通常仕訳'),
    ('adjustment', '決算整理仕訳'),
    ('closing', '決算振替仕訳'),
]

class JournalEntry(models.Model):
    # 既存フィールド
    date = models.DateField()
    summary = models.TextField(blank=True)
    company = models.ForeignKey(Company, ...)

    # 追加フィールド
    entry_type = models.CharField(
        max_length=20,
        choices=ENTRY_TYPE_CHOICES,
        default='normal'
    )
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        on_delete=models.PROTECT,
        related_name='journal_entries'
    )

    class Meta:
        # 決算振替・整理仕訳は期末日のみ
        constraints = [
            models.CheckConstraint(
                check=~(
                    models.Q(entry_type__in=['adjustment', 'closing']) &
                    ~models.Q(date=models.F('fiscal_period__end_date'))
                ),
                name='adjustment_closing_must_be_end_date'
            )
        ]
```

**変更点**:

- ✅ `entry_type`を**JournalEntryに追加**（Accountではない）
- ✅ `fiscal_period`で会計期間を明示的に管理
- ✅ DB制約で決算整理/振替仕訳の日付を期末に強制

### 1.3 Accountモデルの拡張（軽微）

```python
class Account(models.Model):
    # 既存フィールド
    name = models.CharField(max_length=200, unique=True)
    type = models.CharField(max_length=64, choices=ACCOUNT_TYPE_CHOICES)

    # 追加フィールド
    is_adjustment_only = models.BooleanField(default=False)
    # 例: 減価償却累計額、貸倒引当金繰入など決算整理専用科目
```

**理由**:

- 一部の勘定科目は決算整理でのみ使用（減価償却累計額など）
- ただし、ほとんどの科目は通常/決算両方で使用可能

---

## 2. ビジネスロジック設計

### 2.1 決算整理仕訳入力画面の要件

#### 画面構成

```
┌─────────────────────────────────────────┐
│ 決算整理仕訳入力                        │
├─────────────────────────────────────────┤
│ 会計期間: [2025年度▼] (選択可能)       │
│ 日付: 2026-03-31 (自動設定・固定)      │
│ 摘要: [                              ] │
├─────────────────────────────────────────┤
│ 【参考情報】                            │
│ ┌───────────────────────────────────┐ │
│ │ 減価償却費の計算                  │ │
│ │ - 建物: 前期繰越 10,000,000円     │ │
│ │   償却率 0.05 → 500,000円         │ │
│ │ - 備品: 当期取得 2,000,000円      │ │
│ │   償却率 0.2 → 400,000円          │ │
│ │ 合計: 900,000円                   │ │
│ └───────────────────────────────────┘ │
│                                         │
│ ┌───────────────────────────────────┐ │
│ │ 貸倒引当金の計算                  │ │
│ │ - 売掛金残高: 5,000,000円         │ │
│ │   引当率 2% → 100,000円           │ │
│ │ - 前期引当金: 80,000円            │ │
│ │ 繰入額: 20,000円                  │ │
│ └───────────────────────────────────┘ │
├─────────────────────────────────────────┤
│ 借方:                                   │
│  [減価償却費▼] 900,000円               │
│ 貸方:                                   │
│  [減価償却累計額▼] 900,000円           │
└─────────────────────────────────────────┘
```

### 2.2 決算時参考情報の実装方法

**推奨アプローチ: 勘定科目ベースのルールエンジン**

```python
# 新しいモデル: 決算整理ルール
class AdjustmentRule(models.Model):
    """決算整理仕訳の計算ルールを定義"""

    name = models.CharField(max_length=100)  # 例: "減価償却費計算"
    rule_type = models.CharField(
        max_length=50,
        choices=[
            ('depreciation', '減価償却'),
            ('allowance', '引当金'),
            ('inventory', '棚卸資産'),
            ('accrual', '経過勘定'),
        ]
    )
    target_account = models.ForeignKey(Account, on_delete=models.CASCADE)
    calculation_logic = models.JSONField()
    # 例: {"rate": 0.05, "method": "straight_line"}

    is_active = models.BooleanField(default=True)
```

#### 具体的な実装例

```python
# services/adjustment_calculator.py
from decimal import Decimal
from typing import Dict, List

class AdjustmentCalculator:
    """決算整理仕訳の参考情報を計算"""

    @staticmethod
    def calculate_depreciation(
        fiscal_period: FiscalPeriod,
        company: Company
    ) -> Dict:
        """減価償却費を計算"""
        # 1. 固定資産の残高を取得
        asset_accounts = Account.objects.filter(
            type='asset',
            name__contains='建物'  # または固定資産フラグ
        )

        results = []
        for asset in asset_accounts:
            # 2. 期首残高を取得
            opening_balance = get_opening_balance(
                asset, fiscal_period
            )

            # 3. 当期取得額を計算
            current_acquisition = get_period_debits(
                asset, fiscal_period
            )

            # 4. ルールから償却率を取得
            rule = AdjustmentRule.objects.get(
                target_account=asset,
                rule_type='depreciation'
            )
            rate = Decimal(rule.calculation_logic['rate'])

            # 5. 減価償却費を計算
            depreciation = (opening_balance + current_acquisition) * rate

            results.append({
                'asset_name': asset.name,
                'opening_balance': opening_balance,
                'acquisition': current_acquisition,
                'rate': rate,
                'depreciation': depreciation,
            })

        return {
            'items': results,
            'total': sum(r['depreciation'] for r in results),
        }

    @staticmethod
    def calculate_allowance(
        fiscal_period: FiscalPeriod,
        company: Company
    ) -> Dict:
        """貸倒引当金を計算"""
        # 売掛金勘定の残高
        receivables = Account.objects.get(name='売掛金')
        balance = get_account_balance(receivables, fiscal_period.end_date)

        # ルールから引当率を取得
        rule = AdjustmentRule.objects.get(
            target_account=receivables,
            rule_type='allowance'
        )
        rate = Decimal(rule.calculation_logic['rate'])

        # 前期引当金残高
        allowance_account = Account.objects.get(name='貸倒引当金')
        prev_allowance = get_account_balance(
            allowance_account,
            fiscal_period.end_date
        )

        # 当期繰入額
        required = balance * rate
        entry_amount = required - prev_allowance

        return {
            'receivables_balance': balance,
            'rate': rate,
            'required_allowance': required,
            'previous_allowance': prev_allowance,
            'entry_amount': entry_amount,
        }
```

---

## 3. システム設計の全体像

### 3.1 View構成

```python
# views/adjustment_entry.py

class AdjustmentEntryCreateView(JournalEntryFormMixin, CreateView):
    """決算整理仕訳入力ビュー"""
    template_name = "ledger/adjustment_entry/form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 会計期間の選択肢
        context['fiscal_periods'] = FiscalPeriod.objects.filter(
            company=self.request.user.company,
            is_closed=False
        )

        # 選択された会計期間
        period_id = self.request.GET.get('fiscal_period')
        if period_id:
            period = FiscalPeriod.objects.get(id=period_id)
            context['fiscal_period'] = period

            # 参考情報を計算
            calculator = AdjustmentCalculator()
            context['depreciation_info'] = calculator.calculate_depreciation(
                period, self.request.user.company
            )
            context['allowance_info'] = calculator.calculate_allowance(
                period, self.request.user.company
            )
            # 他の整理仕訳情報...

        return context

    def form_valid(self, form):
        # entry_typeを決算整理に固定
        form.instance.entry_type = 'adjustment'

        # 日付を期末日に固定
        period = form.cleaned_data['fiscal_period']
        form.instance.date = period.end_date

        return super().form_valid(form)
```

### 3.2 Form設計

```python
# forms.py

class AdjustmentJournalEntryForm(forms.ModelForm):
    """決算整理仕訳用フォーム"""

    fiscal_period = forms.ModelChoiceField(
        queryset=FiscalPeriod.objects.filter(is_closed=False),
        label="会計期間"
    )

    class Meta:
        model = JournalEntry
        fields = ['fiscal_period', 'summary']
        # dateは自動設定なので除外

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 決算整理用の勘定科目のみを選択肢に
        # (DebitFormSet/CreditFormSetで実装)


class AdjustmentDebitFormSet(BaseInlineFormSet):
    """決算整理仕訳の借方フォームセット"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 通常科目 + 決算整理専用科目を選択可能に
        for form in self.forms:
            form.fields['account'].queryset = Account.objects.filter(
                models.Q(is_adjustment_only=False) |
                models.Q(is_adjustment_only=True)
            )
```

---

## 4. 実装の優先順位

### フェーズ1: 基盤整備

1. ✅ FiscalPeriodモデルの追加
2. ✅ JournalEntryにentry_type, fiscal_periodを追加
3. ✅ 既存データのマイグレーション（デフォルト期間の作成）

### フェーズ2: 基本機能

4. ✅ 通常仕訳入力画面の修正（会計期間選択を追加）
5. ✅ 決算整理仕訳入力画面の作成（最小機能）

### フェーズ3: 参考情報機能

6. ✅ AdjustmentRuleモデルの追加
7. ✅ AdjustmentCalculatorサービスの実装
8. ✅ 減価償却費計算の実装
9. ✅ 貸倒引当金計算の実装
10. ✅ その他整理仕訳（棚卸、経過勘定等）

### フェーズ4: 決算確定機能

11. ✅ 決算振替仕訳の自動生成
12. ✅ 期間締め処理（is_closed=True）

---

## 5. 決算時参考情報の具体的な実装戦略

### 戦略A: ルールベース（推奨）

**メリット**:

- 柔軟性が高い（会社ごとにルールをカスタマイズ可能）
- UI上でルール設定が可能
- 法改正対応が容易

**デメリット**:

- 初期設定が必要

**実装**:

```python
# 管理画面でルールを登録
AdjustmentRule.objects.create(
    name="建物減価償却",
    rule_type="depreciation",
    target_account=building_account,
    calculation_logic={
        "method": "straight_line",
        "rate": 0.05,
        "useful_life": 20
    }
)
```

### 戦略B: 勘定科目命名規則ベース

**メリット**:

- 設定不要で動作

**デメリット**:

- 柔軟性が低い
- 命名規則の強制が必要

**実装例**:

```python
# 科目名から判断
if "減価償却累計額" in account.name:
    # 対応する固定資産科目を推測
    asset_name = account.name.replace("減価償却累計額", "")
    asset_account = Account.objects.get(name=asset_name)
```

### 戦略C: ハイブリッド（最も実用的）

**組み合わせ**:

1. 基本的な整理仕訳はルールベース
2. 簡単なものは命名規則で自動判定
3. 複雑なものは手動入力をサポート

---

## 6. まとめ

### ❌ 避けるべき設計

- Accountにjournal_typeを追加
- JournalEntryの抽象化・継承

### ✅ 推奨する設計

- JournalEntryにentry_typeフィールド追加
- FiscalPeriodモデルの新規作成
- AdjustmentRuleによるルールベースの参考情報計算
- 段階的な実装（まず基本機能、次に参考情報）

### 次のステップ

1. FiscalPeriodモデルの実装
2. JournalEntryの拡張
3. 決算整理仕訳入力画面の基本実装
4. 参考情報計算機能の段階的追加

この設計であれば、会計業務の要件を満たしつつ、保守性の高いシステムが構築できます。
