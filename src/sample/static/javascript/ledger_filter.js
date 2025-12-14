function submitLedger(){
  const name = document.getElementById('account_name').value || '';
  const year = document.getElementById('year').value;

  // URL の逆引きテンプレート（プレースホルダを置換）
  const urlTemplate = "{% url 'general_ledger_by_account' account_name='__PLACEHOLDER__' %}";
  const baseUrl = urlTemplate.replace('__PLACEHOLDER__', encodeURIComponent(name));

  const params = new URLSearchParams();
  if (yearMonth) params.append('year_month', yearMonth);

  const finalUrl = params.toString() ? baseUrl + '?' + params.toString() : baseUrl;

  htmx.ajax('GET', finalUrl, { target: '#search-result', swap: 'innerHTML' });
}
