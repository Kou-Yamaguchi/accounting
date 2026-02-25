/**
 * 決算整理仕訳 仕訳明細テーブル管理
 * 複数の仕訳ブロック（減価償却費・貸倒引当金など）に対応
 */

function initJournalEntryBlock(blockKey, debitPrefix, creditPrefix, debitInitial, creditInitial) {
  debitInitial = debitInitial || [];
  creditInitial = creditInitial || [];

  const debitTotalSelector = `#id_${debitPrefix}-TOTAL_FORMS`;
  const creditTotalSelector = `#id_${creditPrefix}-TOTAL_FORMS`;

  let debitFormCount = parseInt(document.querySelector(debitTotalSelector).value);
  let creditFormCount = parseInt(document.querySelector(creditTotalSelector).value);

  const tbody = document.getElementById(`journal-entry-tbody-${blockKey}`);
  const debitTemplate = document.getElementById(`debit-template-${blockKey}`).innerHTML;
  const creditTemplate = document.getElementById(`credit-template-${blockKey}`).innerHTML;

  const debitRemoveClass = `remove-debit-button-${blockKey}`;
  const creditRemoveClass = `remove-credit-button-${blockKey}`;

  // ソースセルの子要素をターゲットセルに移動する
  function moveContents(target, source) {
    while (source.firstChild) target.appendChild(source.firstChild);
  }

  // 新規行のセルを生成（initial が指定された場合は初期値を設定）
  function createCells(index, isDebit, initial) {
    const prefix = isDebit ? debitPrefix : creditPrefix;
    const template = isDebit ? debitTemplate : creditTemplate;
    const newFormHtml = template.replace(/__prefix__/g, index);
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = newFormHtml;

    const accountField = tempDiv.querySelector('[name*="-account"]');
    const amountField = tempDiv.querySelector('[name*="-amount"]');
    const idField = tempDiv.querySelector('[name*="-id"]');
    const jeField = tempDiv.querySelector('[name*="-journal_entry"]');

    if (initial) {
      if (accountField && initial.account !== undefined && initial.account !== '') {
        accountField.value = initial.account;
      }
      if (amountField && initial.amount !== undefined && initial.amount !== '') {
        amountField.value = initial.amount;
      }
    }

    const accountCell = document.createElement('td');
    const amountCell = document.createElement('td');
    const deleteCell = document.createElement('td');
    deleteCell.className = 'text-center';

    if (idField) accountCell.appendChild(idField);
    if (jeField) accountCell.appendChild(jeField);

    if (accountField) {
      accountCell.appendChild(accountField);
      const accountErrorDiv = document.createElement('div');
      accountErrorDiv.className = 'field-error';
      accountCell.appendChild(accountErrorDiv);
    }
    if (amountField) {
      amountCell.appendChild(amountField);
      const amountErrorDiv = document.createElement('div');
      amountErrorDiv.className = 'field-error';
      amountCell.appendChild(amountErrorDiv);
    }

    const deleteCheckbox = document.createElement('input');
    deleteCheckbox.type = 'checkbox';
    deleteCheckbox.name = `${prefix}-${index}-DELETE`;
    deleteCheckbox.style.display = 'none';
    deleteCell.appendChild(deleteCheckbox);

    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = `btn btn-sm btn-danger ${isDebit ? debitRemoveClass : creditRemoveClass}`;
    deleteBtn.textContent = '削除';
    deleteCell.appendChild(deleteBtn);

    return { accountCell, amountCell, deleteCell };
  }

  // セルを既存行または新規行に追加
  function attachCells(accountCell, amountCell, deleteCell, isDebit) {
    const debitSelector = `[name*="${debitPrefix}"][name*="-account"]`;
    const creditSelector = `[name*="${creditPrefix}"][name*="-account"]`;

    const rows = tbody.querySelectorAll('tr');
    let inserted = false;

    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const occupied = isDebit
        ? row.querySelector(`td:first-child ${debitSelector}`)
        : row.querySelector(`td:nth-child(4) ${creditSelector}`);

      if (!occupied) {
        moveContents(row.children[isDebit ? 0 : 3], accountCell);
        moveContents(row.children[isDebit ? 1 : 4], amountCell);
        moveContents(row.children[isDebit ? 2 : 5], deleteCell);
        inserted = true;
        break;
      }
    }

    if (!inserted) {
      const newRow = createRow();
      moveContents(newRow.children[isDebit ? 0 : 3], accountCell);
      moveContents(newRow.children[isDebit ? 1 : 4], amountCell);
      moveContents(newRow.children[isDebit ? 2 : 5], deleteCell);
      tbody.appendChild(newRow);
    }
  }

  // Django が既にレンダリングした既存フィールドからセルを生成
  function getExistingCells(index, isDebit) {
    const prefix = isDebit ? debitPrefix : creditPrefix;
    const removeCls = isDebit ? debitRemoveClass : creditRemoveClass;

    const accountCell = document.createElement('td');
    const amountCell = document.createElement('td');
    const deleteCell = document.createElement('td');
    deleteCell.className = 'text-center';

    const accountField = document.querySelector(`[name="${prefix}-${index}-account"]`);
    const amountField = document.querySelector(`[name="${prefix}-${index}-amount"]`);
    const idField = document.querySelector(`[name="${prefix}-${index}-id"]`);
    const jeField = document.querySelector(`[name="${prefix}-${index}-journal_entry"]`);
    const deleteField = document.querySelector(`[name="${prefix}-${index}-DELETE"]`);

    if (idField) accountCell.appendChild(idField);
    if (jeField) accountCell.appendChild(jeField);

    if (accountField) {
      const errorList = document.querySelector(`#id_${prefix}-${index}-account + .errorlist`);
      accountCell.appendChild(accountField);
      const errorDiv = document.createElement('div');
      errorDiv.className = 'field-error';
      if (errorList) {
        errorDiv.innerHTML = errorList.innerHTML;
        accountField.classList.add('error-input');
        errorList.remove();
      }
      accountCell.appendChild(errorDiv);
    }

    if (amountField) {
      const errorList = document.querySelector(`#id_${prefix}-${index}-amount + .errorlist`);
      amountCell.appendChild(amountField);
      const errorDiv = document.createElement('div');
      errorDiv.className = 'field-error';
      if (errorList) {
        errorDiv.innerHTML = errorList.innerHTML;
        amountField.classList.add('error-input');
        errorList.remove();
      }
      amountCell.appendChild(errorDiv);
    }

    if (deleteField) {
      deleteField.style.display = 'none';
      deleteCell.appendChild(deleteField);
    }

    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = `btn btn-sm btn-danger ${removeCls}`;
    deleteBtn.textContent = '削除';
    deleteCell.appendChild(deleteBtn);

    return { accountCell, amountCell, deleteCell };
  }

  // テーブルを初期化（既存フォームデータを行に配置）
  function initializeTable(debitCount, creditCount) {
    const maxRows = Math.max(debitCount, creditCount, 1);
    for (let i = 0; i < maxRows; i++) {
      const row = createRow();

      if (i < debitCount) {
        const cells = getExistingCells(i, true);
        moveContents(row.children[0], cells.accountCell);
        moveContents(row.children[1], cells.amountCell);
        moveContents(row.children[2], cells.deleteCell);
      }

      if (i < creditCount) {
        const cells = getExistingCells(i, false);
        moveContents(row.children[3], cells.accountCell);
        moveContents(row.children[4], cells.amountCell);
        moveContents(row.children[5], cells.deleteCell);
      }

      tbody.appendChild(row);
    }

    if (debitCount === 0) {
      document.querySelector(debitTotalSelector).value = 1;
      const cells = createCells(0, true, debitInitial[0]);
      attachCells(cells.accountCell, cells.amountCell, cells.deleteCell, true);
    }

    if (creditCount === 0) {
      document.querySelector(creditTotalSelector).value = 1;
      const cells = createCells(0, false, creditInitial[0]);
      attachCells(cells.accountCell, cells.amountCell, cells.deleteCell, false);
    }

    attachRemoveHandlers();
    updateDeleteButtons();
  }

  // 行を生成
  function createRow() {
    const row = document.createElement('tr');
    row.className = 'journal-entry-row';
    for (let i = 0; i < 6; i++) {
      const cell = document.createElement('td');
      if (i === 2 || i === 5) cell.className = 'text-center';
      row.appendChild(cell);
    }
    return row;
  }

  // 借方行を追加
  document.getElementById(`add-debit-button-${blockKey}`).addEventListener('click', function () {
    const count = parseInt(document.querySelector(debitTotalSelector).value);
    const cells = createCells(count, true);
    attachCells(cells.accountCell, cells.amountCell, cells.deleteCell, true);
    document.querySelector(debitTotalSelector).value = count + 1;
    attachRemoveHandlers();
    updateDeleteButtons();
  });

  // 貸方行を追加
  document.getElementById(`add-credit-button-${blockKey}`).addEventListener('click', function () {
    const count = parseInt(document.querySelector(creditTotalSelector).value);
    const cells = createCells(count, false);
    attachCells(cells.accountCell, cells.amountCell, cells.deleteCell, false);
    document.querySelector(creditTotalSelector).value = count + 1;
    attachRemoveHandlers();
    updateDeleteButtons();
  });

  // 削除ボタンのイベントハンドラを設定
  function attachRemoveHandlers() {
    tbody.querySelectorAll(`.${debitRemoveClass}`).forEach(button => {
      button.onclick = function () {
        const row = this.closest('tr');
        const checkbox = row.querySelector(`input[name*="${debitPrefix}"][name*="DELETE"]`);
        if (checkbox) checkbox.checked = true;
        row.querySelectorAll('td:nth-child(1) *, td:nth-child(2) *').forEach(el => {
          if (el.tagName !== 'INPUT' || el.type !== 'checkbox') el.remove();
        });
        this.remove();
        compactSideRows(true);
        updateDeleteButtons();
      };
    });

    tbody.querySelectorAll(`.${creditRemoveClass}`).forEach(button => {
      button.onclick = function () {
        const row = this.closest('tr');
        const checkbox = row.querySelector(`input[name*="${creditPrefix}"][name*="DELETE"]`);
        if (checkbox) checkbox.checked = true;
        row.querySelectorAll('td:nth-child(4) *, td:nth-child(5) *').forEach(el => {
          if (el.tagName !== 'INPUT' || el.type !== 'checkbox') el.remove();
        });
        this.remove();
        compactSideRows(false);
        updateDeleteButtons();
      };
    });
  }

  // 借方または貸方の行を上に詰める
  function compactSideRows(isDebit) {
    const prefix = isDebit ? debitPrefix : creditPrefix;
    const removeCls = isDebit ? debitRemoveClass : creditRemoveClass;
    const accountColIdx = isDebit ? 1 : 4; // nth-child は 1 始まり
    const amountColIdx = isDebit ? 2 : 5;

    const rows = Array.from(tbody.querySelectorAll('tr'));
    const entries = [];

    rows.forEach(row => {
      const accountField = row.querySelector(
        `td:nth-child(${accountColIdx}) [name*="${prefix}"][name*="-account"]`
      );
      if (accountField) {
        const amountField = row.querySelector(
          `td:nth-child(${amountColIdx}) [name*="${prefix}"][name*="-amount"]`
        );
        const idField = row.querySelector(
          `td:nth-child(${accountColIdx}) [name*="${prefix}"][name*="-id"]`
        );
        const jeField = row.querySelector(
          `td:nth-child(${accountColIdx}) [name*="${prefix}"][name*="-journal_entry"]`
        );
        const deleteField = row.querySelector(`input[name*="${prefix}"][name*="DELETE"]`);
        const deleteButton = row.querySelector(`.${removeCls}`);

        entries.push({ accountField, amountField, idField, jeField, deleteField, deleteButton });

        if (idField) idField.remove();
        if (jeField) jeField.remove();
        if (accountField) accountField.remove();
        if (amountField) amountField.remove();
        if (deleteField) deleteField.remove();
        if (deleteButton) deleteButton.remove();
      }
    });

    const cellIdx = isDebit ? 0 : 3; // children は 0 始まり
    entries.forEach((entry, i) => {
      if (i < rows.length) {
        const row = rows[i];
        if (entry.idField) row.children[cellIdx].appendChild(entry.idField);
        if (entry.jeField) row.children[cellIdx].appendChild(entry.jeField);
        if (entry.accountField) row.children[cellIdx].appendChild(entry.accountField);
        if (entry.amountField) row.children[cellIdx + 1].appendChild(entry.amountField);
        if (entry.deleteField) row.children[cellIdx + 2].appendChild(entry.deleteField);
        if (entry.deleteButton) row.children[cellIdx + 2].appendChild(entry.deleteButton);
      }
    });

    cleanupEmptyRows();
  }

  // 借方・貸方ともに空の行を非表示
  function cleanupEmptyRows() {
    tbody.querySelectorAll('tr').forEach(row => {
      const hasDebit = row.querySelector(`td:nth-child(1) [name*="${debitPrefix}"][name*="-account"]`);
      const hasCredit = row.querySelector(`td:nth-child(4) [name*="${creditPrefix}"][name*="-account"]`);
      if (!hasDebit && !hasCredit) row.style.display = 'none';
    });
  }

  // 削除ボタンの有効/無効を更新（最低1行は残す）
  function updateDeleteButtons() {
    const visibleDebit = Array.from(tbody.querySelectorAll(`.${debitRemoveClass}`))
      .filter(btn => btn.closest('tr').style.display !== 'none');
    const visibleCredit = Array.from(tbody.querySelectorAll(`.${creditRemoveClass}`))
      .filter(btn => btn.closest('tr').style.display !== 'none');

    function setDisabled(buttons, disabled) {
      buttons.forEach(btn => {
        btn.disabled = disabled;
        btn.classList.toggle('disabled', disabled);
        btn.title = disabled ? '最低1行は必要です' : '';
        btn.style.opacity = disabled ? '0.5' : '1';
        btn.style.cursor = disabled ? 'not-allowed' : 'pointer';
      });
    }

    setDisabled(visibleDebit, visibleDebit.length === 1);
    setDisabled(visibleCredit, visibleCredit.length === 1);
  }

  initializeTable(debitFormCount, creditFormCount);
}

// 各ブロックを初期化
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.entry-block').forEach(blockEl => {
    const blockKey = blockEl.dataset.blockKey;
    // data-debit-prefix / data-credit-prefix が指定されている場合はそれを使用
    const debitPrefix = blockEl.dataset.debitPrefix || `${blockKey}-debit`;
    const creditPrefix = blockEl.dataset.creditPrefix || `${blockKey}-credit`;

    let debitInitial = [];
    let creditInitial = [];
    try { debitInitial = JSON.parse(blockEl.dataset.initialDebit || '[]'); } catch (e) {}
    try { creditInitial = JSON.parse(blockEl.dataset.initialCredit || '[]'); } catch (e) {}

    initJournalEntryBlock(blockKey, debitPrefix, creditPrefix, debitInitial, creditInitial);
  });

  // 固定資産登録チェックボックスの表示/非表示制御（他画面との互換性維持）
  const registerCheckbox = document.getElementById('id_register_as_fixed_asset');
  const detailsDiv = document.getElementById('fixed-asset-details');
  if (registerCheckbox && detailsDiv) {
    registerCheckbox.addEventListener('change', function () {
      detailsDiv.style.display = this.checked ? 'block' : 'none';
    });
    if (registerCheckbox.checked) {
      detailsDiv.style.display = 'block';
    }
  }
});
