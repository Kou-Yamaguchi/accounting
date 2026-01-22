# 固定資産台帳の適切な設計

## 1. テーブル設計

### 1.1 固定資産台帳（FixedAsset）

```python
class FixedAsset(models.Model):
    """固定資産台帳"""

    # 基本情報
    name = models.CharField(max_length=255, verbose_name="資産名")
    asset_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="資産番号"
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        limit_choices_to={'type': 'asset'},
        verbose_name="勘定科目"
    )

    # 取得情報
    acquisition_date = models.DateField(verbose_name="取得日")
    acquisition_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="取得価額"
    )
    acquisition_journal_entry = models.ForeignKey(
        'JournalEntry',
        on_delete=models.PROTECT,
        related_name='acquired_assets',
        null=True,
        blank=True,
        verbose_name="取得仕訳"
    )

    # 償却情報
    depreciation_method = models.CharField(
        max_length=20,
        choices=[
            ('straight_line', '定額法'),
            ('declining_balance', '定率法'),
        ],
        default='straight_line',
        verbose_name="償却方法"
    )
    useful_life = models.IntegerField(verbose_name="耐用年数")
    residual_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name="残存価額"
    )

    # ステータス
    status = models.CharField(
        max_length=20,
        choices=[
            ('active', '使用中'),
            ('disposed', '除却済'),
            ('sold', '売却済'),
        ],
        default='active',
        verbose_name="ステータス"
    )
    disposal_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="除却/売却日"
    )
    disposal_journal_entry = models.ForeignKey(
        'JournalEntry',
        on_delete=models.PROTECT,
        related_name='disposed_assets',
        null=True,
        blank=True,
        verbose_name="除却/売却仕訳"
    )

    # メタ情報
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "固定資産"
        verbose_name_plural = "固定資産台帳"
        ordering = ['asset_number']

    def __str__(self):
        return f"{self.asset_number} - {self.name}"

    def calculate_annual_depreciation(self) -> Decimal:
        """年間減価償却費を計算"""
        if self.depreciation_method == 'straight_line':
            return (self.acquisition_cost - self.residual_value) / self.useful_life
        # 定率法の計算も追加可能

    def get_accumulated_depreciation(self, as_of_date: date) -> Decimal:
        """指定日時点での減価償却累計額を取得"""
        # 減価償却履歴から集計
        total = self.depreciation_history.filter(
            fiscal_period__end_date__lte=as_of_date
        ).aggregate(total=Sum('amount'))['total']
        return total or Decimal('0')

    def get_book_value(self, as_of_date: date) -> Decimal:
        """帳簿価額を計算"""
        accumulated = self.get_accumulated_depreciation(as_of_date)
        return self.acquisition_cost - accumulated
```

### 1.2 減価償却履歴（DepreciationHistory）

```python
class DepreciationHistory(models.Model):
    """減価償却の履歴を記録"""

    fixed_asset = models.ForeignKey(
        FixedAsset,
        on_delete=models.CASCADE,
        related_name='depreciation_history',
        verbose_name="固定資産"
    )
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        on_delete=models.PROTECT,
        verbose_name="会計期間"
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="償却額"
    )
    depreciation_journal_entry = models.OneToOneField(
        'JournalEntry',
        on_delete=models.PROTECT,
        related_name='depreciation_record',
        null=True,
        blank=True,
        verbose_name="減価償却仕訳"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "減価償却履歴"
        verbose_name_plural = "減価償却履歴"
        unique_together = [['fixed_asset', 'fiscal_period']]
        ordering = ['-fiscal_period__end_date']

    def __str__(self):
        return f"{self.fixed_asset.name} - {self.fiscal_period.name}: {self.amount}"
```

---

## 2. データフロー

### 2.1 固定資産取得時

```
ステップ1: 仕訳入力
┌─────────────────────────────┐
│ 借方: 備品 100,000          │
│ 貸方: 現金 100,000          │
│ 摘要: ノートPC購入          │
└─────────────────────────────┘
         ↓ 保存
    JournalEntry(id=123)

ステップ2: 固定資産登録（同時 or 別画面）
┌─────────────────────────────┐
│ 資産名: ノートPC A          │
│ 取得価額: 100,000           │
│ 取得日: 2025-04-01          │
│ 耐用年数: 4年               │
│ 償却方法: 定額法            │
│ 取得仕訳: #123 ←紐づけ      │
└─────────────────────────────┘
         ↓ 保存
    FixedAsset(id=456, acquisition_journal_entry_id=123)
```

### 2.2 決算整理仕訳入力時

```
ステップ1: 固定資産台帳から減価償却費を計算
┌───────────────────────────────────┐
│ 【減価償却費計算】               │
│ ノートPC A                       │
│  取得価額: 100,000円             │
│  耐用年数: 4年                   │
│  年間償却額: 25,000円            │
│  帳簿価額: 75,000円              │
│                                  │
│ サーバー B                       │
│  取得価額: 500,000円             │
│  耐用年数: 5年                   │
│  年間償却額: 100,000円           │
│  帳簿価額: 400,000円             │
│                                  │
│ 合計償却額: 125,000円            │
└───────────────────────────────────┘

ステップ2: 決算整理仕訳を作成
┌─────────────────────────────┐
│ 借方: 減価償却費 125,000    │
│ 貸方: 減価償却累計額 125,000│
└─────────────────────────────┘
         ↓ 保存
    JournalEntry(id=789, entry_type='adjustment')

ステップ3: 減価償却履歴を記録
    DepreciationHistory(
        fixed_asset_id=456,
        amount=25000,
        depreciation_journal_entry_id=789
    )
```

---

## 3. 実装方法

### 3.1 固定資産取得画面の設計

#### オプションA: 仕訳入力画面に組み込む（推奨）

```python
# forms.py
class FixedAssetInlineForm(forms.ModelForm):
    """固定資産情報の入力フォーム（仕訳入力と同時）"""

    is_fixed_asset = forms.BooleanField(
        required=False,
        label="固定資産として登録"
    )

    class Meta:
        model = FixedAsset
        fields = [
            'name', 'asset_number', 'account',
            'useful_life', 'depreciation_method'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 取得価額は仕訳の金額から自動設定
        # 取得日は仕訳の日付から自動設定

# views.py
class JournalEntryCreateView(JournalEntryFormMixin, CreateView):

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fixed_asset_form'] = FixedAssetInlineForm()
        return context

    def form_valid(self, form):
        # 仕訳を保存
        response = super().form_valid(form)

        # 固定資産登録フラグがONの場合
        fixed_asset_form = FixedAssetInlineForm(self.request.POST)
        if fixed_asset_form.cleaned_data.get('is_fixed_asset'):
            fixed_asset = fixed_asset_form.save(commit=False)
            fixed_asset.acquisition_journal_entry = self.object
            fixed_asset.acquisition_date = self.object.date
            # 取得価額は借方明細から取得
            debit = self.object.debits.first()
            fixed_asset.acquisition_cost = debit.amount
            fixed_asset.account = debit.account
            fixed_asset.save()

        return response
```

#### オプションB: 別画面で管理

```python
class FixedAssetCreateView(CreateView):
    """固定資産登録画面（仕訳とは別）"""
    model = FixedAsset
    fields = [
        'name', 'asset_number', 'account',
        'acquisition_date', 'acquisition_cost',
        'useful_life', 'depreciation_method',
        'acquisition_journal_entry'
    ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # 取得仕訳の選択肢を固定資産科目の仕訳のみに限定
        form.fields['acquisition_journal_entry'].queryset = (
            JournalEntry.objects.filter(
                debits__account__type='asset',
                debits__account__name__in=['備品', '建物', '車両運搬具']
            ).distinct()
        )
        return form
```

### 3.2 決算整理仕訳の参考情報計算

```python
# services/adjustment_calculator.py

class AdjustmentCalculator:

    @staticmethod
    def calculate_depreciation(
        fiscal_period: FiscalPeriod,
        company: Company
    ) -> Dict:
        """減価償却費を計算"""

        # 当期に使用中の固定資産を取得
        assets = FixedAsset.objects.filter(
            company=company,
            status='active',
            acquisition_date__lte=fiscal_period.end_date
        ).select_related('account')

        results = []
        total_depreciation = Decimal('0')

        for asset in assets:
            # 既に当期の減価償却が計上済みかチェック
            existing = DepreciationHistory.objects.filter(
                fixed_asset=asset,
                fiscal_period=fiscal_period
            ).first()

            if existing:
                # 既に計上済み
                amount = existing.amount
            else:
                # 新規計算
                amount = asset.calculate_annual_depreciation()

                # 月割計算（期中取得の場合）
                if asset.acquisition_date > fiscal_period.start_date:
                    months = calculate_months_in_period(
                        asset.acquisition_date,
                        fiscal_period.end_date
                    )
                    amount = amount * months / 12

            book_value = asset.get_book_value(fiscal_period.end_date)

            results.append({
                'asset_number': asset.asset_number,
                'asset_name': asset.name,
                'acquisition_cost': asset.acquisition_cost,
                'useful_life': asset.useful_life,
                'annual_depreciation': amount,
                'accumulated_depreciation': asset.get_accumulated_depreciation(
                    fiscal_period.end_date
                ),
                'book_value': book_value,
                'already_recorded': existing is not None,
            })

            total_depreciation += amount

        return {
            'assets': results,
            'total_depreciation': total_depreciation,
        }
```

### 3.3 決算整理仕訳入力画面

```python
class AdjustmentEntryCreateView(CreateView):
    """決算整理仕訳入力"""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        period_id = self.request.GET.get('fiscal_period')
        if period_id:
            period = FiscalPeriod.objects.get(id=period_id)
            calculator = AdjustmentCalculator()

            # 減価償却費の参考情報
            context['depreciation_info'] = calculator.calculate_depreciation(
                period, self.request.user.company
            )

        return context

    def form_valid(self, form):
        response = super().form_valid(form)

        # 減価償却仕訳の場合、履歴を記録
        if '減価償却' in form.cleaned_data['summary']:
            # 各固定資産の減価償却履歴を作成
            # （実装の詳細は割愛）
            pass

        return response
```

---

## 4. データベース設計のまとめ

### リレーション図

```
┌─────────────────┐
│  FiscalPeriod   │
└────────┬────────┘
         │ 1
         │
         │ *
┌────────┴────────┐         ┌──────────────┐
│  JournalEntry   │         │   Account    │
│  ─────────────  │         └──────┬───────┘
│  entry_type     │                │
│  fiscal_period ─┼──┐             │
└────┬────────────┘  │             │
     │               │             │
     │               │             │
     │ *             │ 1           │ 1
     │               │             │
┌────┴─────────┐     │     ┌───────┴──────────────┐
│FixedAsset    │     │     │                      │
│──────────────│     └────►│   FixedAsset         │
│acquisition_  │           │   ──────────         │
│journal_entry │◄──────────┤   account            │
│              │           │   acquisition_       │
│disposal_     │           │   journal_entry      │
│journal_entry │◄──────────┤   disposal_          │
└──────┬───────┘           │   journal_entry      │
       │                   └──────────────────────┘
       │ 1
       │
       │ *
┌──────┴────────────────┐
│DepreciationHistory    │
│───────────────────────│
│fixed_asset            │
│fiscal_period          │
│depreciation_          │
│journal_entry          │
└───────────────────────┘
```

---

## 5. 比較: 提案された設計 vs 推奨設計

| 観点                   | 提案設計                     | 推奨設計                      |
| ---------------------- | ---------------------------- | ----------------------------- |
| **リレーション**       | JournalEntry → FixedAsset    | FixedAsset → JournalEntry     |
| **1対多の対応**        | 不可（1仕訳に1固定資産のみ） | 可能（1仕訳で複数資産取得可） |
| **NULL値**             | 大量に発生                   | 最小限                        |
| **減価償却履歴**       | 管理困難                     | 専用テーブルで明確に管理      |
| **帳簿価額計算**       | 複雑                         | シンプル                      |
| **会計業務との整合性** | 低い                         | 高い                          |

---

## 6. 実装の優先順位

### フェーズ1: 基本機能

1. ✅ FixedAssetモデルの作成
2. ✅ DepreciationHistoryモデルの作成
3. ✅ マイグレーション実行

### フェーズ2: 登録機能

4. ✅ 固定資産登録画面（別画面方式）
5. ✅ 固定資産一覧・編集・削除機能

### フェーズ3: 決算連携

6. ✅ AdjustmentCalculatorの実装
7. ✅ 決算整理仕訳画面への参考情報表示
8. ✅ 減価償却履歴の自動記録

### フェーズ4: 高度な機能（オプション）

9. ✅ 仕訳入力時の固定資産同時登録
10. ✅ 固定資産売却・除却処理
11. ✅ 固定資産台帳レポート出力

---

## 7. まとめ

### ❌ 避けるべき設計

- JournalEntryに`fixed_asset_id`を直接追加
- 1:1のリレーション前提

### ✅ 推奨する設計

- FixedAssetを独立したマスタとして管理
- FixedAsset → JournalEntryの参照
- DepreciationHistoryで減価償却の履歴を明確に管理
- 会計業務の実態に即したデータモデル

この設計により、実務に即した固定資産管理と減価償却計算が実現できます。
