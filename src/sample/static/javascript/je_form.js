document.addEventListener('DOMContentLoaded', function() {
  let debitFormCount = parseInt(document.querySelector('#id_debits-TOTAL_FORMS').value);
  let creditFormCount = parseInt(document.querySelector('#id_credits-TOTAL_FORMS').value);
  
  const tbody = document.getElementById('journal-entry-tbody');
  const debitTemplate = document.getElementById('debit-template').innerHTML;
  const creditTemplate = document.getElementById('credit-template').innerHTML;

  function createDebitCells(index) {
    const newFormHtml = debitTemplate.replace(/__prefix__/g, index);
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = newFormHtml;
    
    const accountField = tempDiv.querySelector('[name*="-account"]');
    const amountField = tempDiv.querySelector('[name*="-amount"]');
    const idField = tempDiv.querySelector('[name*="-id"]');
    const jeField = tempDiv.querySelector('[name*="-journal_entry"]');
    
    const debitAccountCell = document.createElement('td');
    const debitAmountCell = document.createElement('td');
    const debitDeleteCell = document.createElement('td');
    debitDeleteCell.className = 'text-center';
    
    if (idField) debitAccountCell.appendChild(idField);
    if (jeField) debitAccountCell.appendChild(jeField);
    if (accountField) {
      debitAccountCell.appendChild(accountField);
      // エラー表示用のdivを追加
      const accountErrorDiv = document.createElement('div');
      accountErrorDiv.className = 'field-error';
      accountErrorDiv.id = `debit-${index}-account-error`;
      debitAccountCell.appendChild(accountErrorDiv);
    }
    if (amountField) {
      debitAmountCell.appendChild(amountField);
      // エラー表示用のdivを追加
      const amountErrorDiv = document.createElement('div');
      amountErrorDiv.className = 'field-error';
      amountErrorDiv.id = `debit-${index}-amount-error`;
      debitAmountCell.appendChild(amountErrorDiv);
    }
    
    const deleteCheckbox = document.createElement('input');
    deleteCheckbox.type = 'checkbox';
    deleteCheckbox.name = `debits-${index}-DELETE`;
    deleteCheckbox.style.display = 'none';
    debitDeleteCell.appendChild(deleteCheckbox);
    
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'btn btn-sm btn-danger remove-debit-button';
    deleteBtn.textContent = '削除';
    debitDeleteCell.appendChild(deleteBtn);

    return {debitAccountCell, debitAmountCell, debitDeleteCell};
  }

  function createCreditCells(index) {
    const newFormHtml = creditTemplate.replace(/__prefix__/g, index);
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = newFormHtml;
    
    const accountField = tempDiv.querySelector('[name*="-account"]');
    const amountField = tempDiv.querySelector('[name*="-amount"]');
    const idField = tempDiv.querySelector('[name*="-id"]');
    const jeField = tempDiv.querySelector('[name*="-journal_entry"]');
    
    const creditAccountCell = document.createElement('td');
    const creditAmountCell = document.createElement('td');
    const creditDeleteCell = document.createElement('td');
    creditDeleteCell.className = 'text-center';
    
    if (idField) creditAccountCell.appendChild(idField);
    if (jeField) creditAccountCell.appendChild(jeField);
    if (accountField) {
      creditAccountCell.appendChild(accountField);
      // エラー表示用のdivを追加
      const accountErrorDiv = document.createElement('div');
      accountErrorDiv.className = 'field-error';
      accountErrorDiv.id = `credit-${index}-account-error`;
      creditAccountCell.appendChild(accountErrorDiv);
    }
    if (amountField) {
      creditAmountCell.appendChild(amountField);
      // エラー表示用のdivを追加
      const amountErrorDiv = document.createElement('div');
      amountErrorDiv.className = 'field-error';
      amountErrorDiv.id = `credit-${index}-amount-error`;
      creditAmountCell.appendChild(amountErrorDiv);
    }
    
    const deleteCheckbox = document.createElement('input');
    deleteCheckbox.type = 'checkbox';
    deleteCheckbox.name = `credits-${index}-DELETE`;
    deleteCheckbox.style.display = 'none';
    creditDeleteCell.appendChild(deleteCheckbox);
    
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'btn btn-sm btn-danger remove-credit-button';
    deleteBtn.textContent = '削除';
    creditDeleteCell.appendChild(deleteBtn);

    return {creditAccountCell, creditAmountCell, creditDeleteCell};
  }

  function attatchDebitCells(debitAccountCell, debitAmountCell, debitDeleteCell) {
    function attachContents(targetCell, sourceCell) {
      while (sourceCell.firstChild) {
        targetCell.appendChild(sourceCell.firstChild);
      }
    }
    const rows = tbody.querySelectorAll('tr');
    let inserted = false;
    
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const debitAccount = row.querySelector('td:first-child [name*="debits"][name*="-account"]');
      
      if (!debitAccount) {
        // この行には借方がないので、借方セルを追加
        attachContents(row.children[0], debitAccountCell);
        attachContents(row.children[1], debitAmountCell);
        attachContents(row.children[2], debitDeleteCell);
        inserted = true;
        break;
      }
    }
    
    // 空きがなければ新しい行を追加
    if (!inserted) {
      const newRow = createRow();
      attachContents(newRow.children[0], debitAccountCell);
      attachContents(newRow.children[1], debitAmountCell);
      attachContents(newRow.children[2], debitDeleteCell);
      tbody.appendChild(newRow);
    }
  }

  function attatchCreditCells(creditAccountCell, creditAmountCell, creditDeleteCell) {
    function attachContents(targetCell, sourceCell) {
      while (sourceCell.firstChild) {
        targetCell.appendChild(sourceCell.firstChild);
      }
    }
    const rows = tbody.querySelectorAll('tr');
    let inserted = false;
    
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const creditAccount = row.querySelector('td:nth-child(4) [name*="credits"][name*="-account"]');
      
      if (!creditAccount) {
        // この行には貸方がないので、貸方セルを追加
        attachContents(row.children[3], creditAccountCell);
        attachContents(row.children[4], creditAmountCell);
        attachContents(row.children[5], creditDeleteCell);
        inserted = true;
        break;
      }
    }
    
    // 空きがなければ新しい行を追加
    if (!inserted) {
      const newRow = createRow();
      attachContents(newRow.children[3], creditAccountCell);
      attachContents(newRow.children[4], creditAmountCell);
      attachContents(newRow.children[5], creditDeleteCell);
      tbody.appendChild(newRow);
    }
  }

  // 既存の借方フィールドを取得（Djangoが既にレンダリング済み）
  function getExistingDebitCells(index) {
    const accountCell = document.createElement('td');
    const amountCell = document.createElement('td');
    const deleteCell = document.createElement('td');
    deleteCell.className = 'text-center';
    console.log(`Getting existing debit cells for index ${index}`);
    // Djangoが生成した既存のフィールドを取得
    const accountField = document.querySelector(`[name="debits-${index}-account"]`);
    const amountField = document.querySelector(`[name="debits-${index}-amount"]`);
    const idField = document.querySelector(`[name="debits-${index}-id"]`);
    const jeField = document.querySelector(`[name="debits-${index}-journal_entry"]`);
    const deleteField = document.querySelector(`[name="debits-${index}-DELETE"]`);
    
    // 既存フィールドをセルに追加（値は既に入っている）
    console.log(`Getting existing debit cells for index ${accountField}`);
    if (idField) accountCell.appendChild(idField);
    if (jeField) accountCell.appendChild(jeField);
    if (accountField) {
      // エラーリストを先に取得してから移動
      const accountErrorList = document.querySelector(`#id_debits-${index}-account + .errorlist`);
      accountCell.appendChild(accountField);
      // エラー表示用のdivを追加
      const accountErrorDiv = document.createElement('div');
      accountErrorDiv.className = 'field-error';
      accountErrorDiv.id = `debit-${index}-account-error`;
      
      // Djangoから渡されたエラーを表示
      if (accountErrorList) {
        accountErrorDiv.innerHTML = accountErrorList.innerHTML;
        accountField.classList.add('error-input');
        accountErrorList.remove(); // 元のエラーリストを削除
      }
      accountCell.appendChild(accountErrorDiv);
    }
    if (amountField) {
      // エラーリストを先に取得してから移動
      const amountErrorList = document.querySelector(`#id_debits-${index}-amount + .errorlist`);
      amountCell.appendChild(amountField);
      // エラー表示用のdivを追加
      const amountErrorDiv = document.createElement('div');
      amountErrorDiv.className = 'field-error';
      amountErrorDiv.id = `debit-${index}-amount-error`;
      
      // Djangoから渡されたエラーを表示
      if (amountErrorList) {
        amountErrorDiv.innerHTML = amountErrorList.innerHTML;
        amountField.classList.add('error-input');
        amountErrorList.remove(); // 元のエラーリストを削除
      }
      amountCell.appendChild(amountErrorDiv);
    }
    
    if (deleteField) {
      deleteField.style.display = 'none';
      deleteCell.appendChild(deleteField);
    }
    
    // 削除ボタン
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'btn btn-sm btn-danger remove-debit-button';
    deleteBtn.textContent = '削除';
    deleteCell.appendChild(deleteBtn);
    
    return { accountCell, amountCell, deleteCell };
  }

  // 既存の貸方フィールドを取得
  function getExistingCreditCells(index) {
    const accountCell = document.createElement('td');
    const amountCell = document.createElement('td');
    const deleteCell = document.createElement('td');
    deleteCell.className = 'text-center';
    
    const accountField = document.querySelector(`[name="credits-${index}-account"]`);
    const amountField = document.querySelector(`[name="credits-${index}-amount"]`);
    const idField = document.querySelector(`[name="credits-${index}-id"]`);
    const jeField = document.querySelector(`[name="credits-${index}-journal_entry"]`);
    const deleteField = document.querySelector(`[name="credits-${index}-DELETE"]`);
    
    if (idField) accountCell.appendChild(idField);
    if (jeField) accountCell.appendChild(jeField);
    if (accountField) {
      // エラーリストを先に取得してから移動
      const accountErrorList = document.querySelector(`#id_credits-${index}-account + .errorlist`);
      accountCell.appendChild(accountField);
      // エラー表示用のdivを追加
      const accountErrorDiv = document.createElement('div');
      accountErrorDiv.className = 'field-error';
      accountErrorDiv.id = `credit-${index}-account-error`;
      
      // Djangoから渡されたエラーを表示
      if (accountErrorList) {
        accountErrorDiv.innerHTML = accountErrorList.innerHTML;
        accountField.classList.add('error-input');
        accountErrorList.remove(); // 元のエラーリストを削除
      }
      accountCell.appendChild(accountErrorDiv);
    }
    if (amountField) {
      // エラーリストを先に取得してから移動
      const amountErrorList = document.querySelector(`#id_credits-${index}-amount + .errorlist`);
      amountCell.appendChild(amountField);
      // エラー表示用のdivを追加
      const amountErrorDiv = document.createElement('div');
      amountErrorDiv.className = 'field-error';
      amountErrorDiv.id = `credit-${index}-amount-error`;
      
      // Djangoから渡されたエラーを表示
      if (amountErrorList) {
        amountErrorDiv.innerHTML = amountErrorList.innerHTML;
        amountField.classList.add('error-input');
        amountErrorList.remove(); // 元のエラーリストを削除
      }
      amountCell.appendChild(amountErrorDiv);
    }
    
    if (deleteField) {
      deleteField.style.display = 'none';
      deleteCell.appendChild(deleteField);
    }
    
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'btn btn-sm btn-danger remove-credit-button';
    deleteBtn.textContent = '削除';
    deleteCell.appendChild(deleteBtn);
    
    return { accountCell, amountCell, deleteCell };
  }

  // 初期データをテーブルに表示
  function initializeTable(debitCount = debitFormCount, creditCount = creditFormCount) {
    const maxRows = Math.max(debitCount, creditCount, 1); // 最低1行
    for (let i = 0; i < maxRows; i++) {
      const row = createRow();

      if (i < debitCount) {
        const debitCells = getExistingDebitCells(i);
        row.children[0].appendChild(debitCells.accountCell);
        row.children[1].appendChild(debitCells.amountCell);
        row.children[2].appendChild(debitCells.deleteCell);
      }

      if (i < creditCount) {
        const creditCells = getExistingCreditCells(i);
        row.children[3].appendChild(creditCells.accountCell);
        row.children[4].appendChild(creditCells.amountCell);
        row.children[5].appendChild(creditCells.deleteCell);
      }

      tbody.appendChild(row);
    }
    // 初期フォームカウントが0の場合、1に設定
    if (debitCount === 0) {
      debitCount = 1;
      document.querySelector('#id_debits-TOTAL_FORMS').value = debitCount;
      const cells = createDebitCells(0);
      attatchDebitCells(cells.debitAccountCell, cells.debitAmountCell, cells.debitDeleteCell);
    }

    if (creditCount === 0) {
      creditCount = 1;
      document.querySelector('#id_credits-TOTAL_FORMS').value = creditCount;
      const cells = createCreditCells(0);
      attatchCreditCells(cells.creditAccountCell, cells.creditAmountCell, cells.creditDeleteCell);
    }

    attachRemoveHandlers();
    updateDeleteButtons();
  }
  
  // 行を作成
  function createRow() {
    const row = document.createElement('tr');
    row.className = 'journal-entry-row';
    
    // 借方セル
    const debitAccountCell = document.createElement('td');
    const debitAmountCell = document.createElement('td');
    const debitDeleteCell = document.createElement('td');
    debitDeleteCell.className = 'text-center';
    
    // 貸方セル
    const creditAccountCell = document.createElement('td');
    const creditAmountCell = document.createElement('td');
    const creditDeleteCell = document.createElement('td');
    creditDeleteCell.className = 'text-center';
    
    row.appendChild(debitAccountCell);
    row.appendChild(debitAmountCell);
    row.appendChild(debitDeleteCell);
    row.appendChild(creditAccountCell);
    row.appendChild(creditAmountCell);
    row.appendChild(creditDeleteCell);
    
    return row;
  }
  
  // 借方行を追加
  document.getElementById('add-debit-button').addEventListener('click', function () {
    const formCount = parseInt(document.querySelector('#id_debits-TOTAL_FORMS').value);
    const { debitAccountCell, debitAmountCell, debitDeleteCell } = createDebitCells(formCount);
    attatchDebitCells(debitAccountCell, debitAmountCell, debitDeleteCell);
    
    document.querySelector('#id_debits-TOTAL_FORMS').value = formCount + 1;
    
    attachRemoveHandlers();
    updateDeleteButtons();
  });
  
  // 貸方行を追加
  document.getElementById('add-credit-button').addEventListener('click', function () {
    const formCount = parseInt(document.querySelector('#id_credits-TOTAL_FORMS').value);
    const { creditAccountCell, creditAmountCell, creditDeleteCell } = createCreditCells(formCount);
    attatchCreditCells(creditAccountCell, creditAmountCell, creditDeleteCell);
    
    document.querySelector('#id_credits-TOTAL_FORMS').value = formCount + 1;
    
    attachRemoveHandlers();
    updateDeleteButtons();
  });
  
  // 削除ボタンのイベントハンドラを設定
  function attachRemoveHandlers() {
    document.querySelectorAll('.remove-debit-button').forEach(button => {
      button.onclick = function() {
        const row = this.closest('tr');
        const deleteCheckbox = row.querySelector('input[name*="debits"][name*="DELETE"]');
        if (deleteCheckbox) {
          deleteCheckbox.checked = true;
        }
        // 借方のフォームフィールドをクリア（視覚的に削除）
        const debitFields = row.querySelectorAll('td:nth-child(1) *, td:nth-child(2) *');
        debitFields.forEach(field => {
          if (field.tagName !== 'INPUT' || field.type !== 'checkbox') {
            field.remove();
          }
        });
        // 削除ボタンも削除
        this.remove();
        
        // 借方を上に詰める
        compactDebitRows();
        updateDeleteButtons();
      };
    });
    
    document.querySelectorAll('.remove-credit-button').forEach(button => {
      button.onclick = function() {
        const row = this.closest('tr');
        const deleteCheckbox = row.querySelector('input[name*="credits"][name*="DELETE"]');
        if (deleteCheckbox) {
          deleteCheckbox.checked = true;
        }
        // 貸方のフォームフィールドをクリア（視覚的に削除）
        const creditFields = row.querySelectorAll('td:nth-child(4) *, td:nth-child(5) *');
        creditFields.forEach(field => {
          if (field.tagName !== 'INPUT' || field.type !== 'checkbox') {
            field.remove();
          }
        });
        // 削除ボタンも削除
        this.remove();
        
        // 貸方を上に詰める
        compactCreditRows();
        updateDeleteButtons();
      };
    });
  }
  
  // 借方行を上に詰める
  function compactDebitRows() {
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const debits = [];
    
    // すべての借方フィールドを収集
    rows.forEach(row => {
      const accountField = row.querySelector('td:nth-child(1) [name*="debits"][name*="-account"]');
      if (accountField) {
        const amountField = row.querySelector('td:nth-child(2) [name*="debits"][name*="-amount"]');
        const idField = row.querySelector('td:nth-child(1) [name*="debits"][name*="-id"]');
        const jeField = row.querySelector('td:nth-child(1) [name*="debits"][name*="-journal_entry"]');
        const deleteField = row.querySelector('input[name*="debits"][name*="DELETE"]');
        const deleteButton = row.querySelector('.remove-debit-button');
        
        debits.push({
          accountField,
          amountField,
          idField,
          jeField,
          deleteField,
          deleteButton
        });
        
        // 既存のフィールドを削除
        if (idField) idField.remove();
        if (jeField) jeField.remove();
        if (accountField) accountField.remove();
        if (amountField) amountField.remove();
        if (deleteField) deleteField.remove();
        if (deleteButton) deleteButton.remove();
      }
    });
    
    // 借方を詰めて再配置
    debits.forEach((debit, index) => {
      if (index < rows.length) {
        const row = rows[index];
        const accountCell = row.children[0];
        const amountCell = row.children[1];
        const deleteCell = row.children[2];
        
        if (debit.idField) accountCell.appendChild(debit.idField);
        if (debit.jeField) accountCell.appendChild(debit.jeField);
        if (debit.accountField) accountCell.appendChild(debit.accountField);
        if (debit.amountField) amountCell.appendChild(debit.amountField);
        if (debit.deleteField) deleteCell.appendChild(debit.deleteField);
        if (debit.deleteButton) deleteCell.appendChild(debit.deleteButton);
      }
    });
    
    // 空行を削除または非表示
    cleanupEmptyRows();
  }
  
  // 貸方行を上に詰める
  function compactCreditRows() {
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const credits = [];
    
    // すべての貸方フィールドを収集
    rows.forEach(row => {
      const accountField = row.querySelector('td:nth-child(4) [name*="credits"][name*="-account"]');
      if (accountField) {
        const amountField = row.querySelector('td:nth-child(5) [name*="credits"][name*="-amount"]');
        const idField = row.querySelector('td:nth-child(4) [name*="credits"][name*="-id"]');
        const jeField = row.querySelector('td:nth-child(4) [name*="credits"][name*="-journal_entry"]');
        const deleteField = row.querySelector('input[name*="credits"][name*="DELETE"]');
        const deleteButton = row.querySelector('.remove-credit-button');
        
        credits.push({
          accountField,
          amountField,
          idField,
          jeField,
          deleteField,
          deleteButton
        });
        
        // 既存のフィールドを削除
        if (idField) idField.remove();
        if (jeField) jeField.remove();
        if (accountField) accountField.remove();
        if (amountField) amountField.remove();
        if (deleteField) deleteField.remove();
        if (deleteButton) deleteButton.remove();
      }
    });
    
    // 貸方を詰めて再配置
    credits.forEach((credit, index) => {
      if (index < rows.length) {
        const row = rows[index];
        const accountCell = row.children[3];
        const amountCell = row.children[4];
        const deleteCell = row.children[5];
        
        if (credit.idField) accountCell.appendChild(credit.idField);
        if (credit.jeField) accountCell.appendChild(credit.jeField);
        if (credit.accountField) accountCell.appendChild(credit.accountField);
        if (credit.amountField) amountCell.appendChild(credit.amountField);
        if (credit.deleteField) deleteCell.appendChild(credit.deleteField);
        if (credit.deleteButton) deleteCell.appendChild(credit.deleteButton);
      }
    });
    
    // 空行を削除または非表示
    cleanupEmptyRows();
  }
  
  // 借方・貸方両方とも空欄の行を削除または非表示
  function cleanupEmptyRows() {
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    rows.forEach(row => {
      const hasDebit = row.querySelector('td:nth-child(1) [name*="debits"][name*="-account"]');
      const hasCredit = row.querySelector('td:nth-child(4) [name*="credits"][name*="-account"]');
      
      if (!hasDebit && !hasCredit) {
        row.style.display = 'none';
      }
    });
  }
  
  // 削除ボタンの有効/無効を更新
  function updateDeleteButtons() {
    // 表示中の借方の数をカウント
    const visibleDebitButtons = Array.from(document.querySelectorAll('.remove-debit-button')).filter(btn => {
      return btn.closest('tr').style.display !== 'none';
    });
    
    // 表示中の貸方の数をカウント
    const visibleCreditButtons = Array.from(document.querySelectorAll('.remove-credit-button')).filter(btn => {
      return btn.closest('tr').style.display !== 'none';
    });
    
    // 借方が1つだけの場合、削除ボタンを無効化
    if (visibleDebitButtons.length === 1) {
      visibleDebitButtons[0].disabled = true;
      visibleDebitButtons[0].classList.add('disabled');
      visibleDebitButtons[0].title = '最低1行は必要です';
      visibleDebitButtons[0].style.opacity = '0.5';
      visibleDebitButtons[0].style.cursor = 'not-allowed';
    } else {
      visibleDebitButtons.forEach(btn => {
        btn.disabled = false;
        btn.classList.remove('disabled');
        btn.title = '';
        btn.style.opacity = '1';
        btn.style.cursor = 'pointer';
      });
    }
    
    // 貸方が1つだけの場合、削除ボタンを無効化
    if (visibleCreditButtons.length === 1) {
      visibleCreditButtons[0].disabled = true;
      visibleCreditButtons[0].classList.add('disabled');
      visibleCreditButtons[0].title = '最低1行は必要です';
      visibleCreditButtons[0].style.opacity = '0.5';
      visibleCreditButtons[0].style.cursor = 'not-allowed';
    } else {
      visibleCreditButtons.forEach(btn => {
        btn.disabled = false;
        btn.classList.remove('disabled');
        btn.title = '';
        btn.style.opacity = '1';
        btn.style.cursor = 'pointer';
      });
    }
  }
  
  // 初期化
  initializeTable();
  
  // 固定資産登録チェックボックスの表示/非表示制御
  const registerCheckbox = document.getElementById('id_register_as_fixed_asset');
  const detailsDiv = document.getElementById('fixed-asset-details');
  if (registerCheckbox && detailsDiv) {
    registerCheckbox.addEventListener('change', function() {
      detailsDiv.style.display = this.checked ? 'block' : 'none';
    });
    
    if (registerCheckbox.checked) {
      detailsDiv.style.display = 'block';
    }
  }
});
