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
    if (accountField) debitAccountCell.appendChild(accountField);
    if (amountField) debitAmountCell.appendChild(amountField);
    
    const deleteCheckbox = document.createElement('input');
    deleteCheckbox.type = 'checkbox';
    deleteCheckbox.name = `debits-${debitFormCount}-DELETE`;
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
    if (accountField) creditAccountCell.appendChild(accountField);
    if (amountField) creditAmountCell.appendChild(amountField);
    
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
  
  // 初期データをテーブルに表示
  function initializeTable(debitCount = debitFormCount, creditCount = creditFormCount) {
    const maxRows = Math.max(debitCount, creditCount, 1); // 最低1行
    for (let i = 0; i < maxRows; i++) {
      const row = createRow();
      tbody.appendChild(row);
    }
    // 初期フォームカウントが0の場合、1に設定
    if (debitCount === 0) {
      debitCount = 1;
      document.querySelector('#id_debits-TOTAL_FORMS').value = debitCount;
    }

    for (let i = 0; i < debitCount; i++) {
      const cells = createDebitCells(i);
      attatchDebitCells(cells.debitAccountCell, cells.debitAmountCell, cells.debitDeleteCell);
    }

    if (creditCount === 0) {
      creditCount = 1;
      document.querySelector('#id_credits-TOTAL_FORMS').value = creditCount;
    }

    for (let i = 0; i < creditCount; i++) {
      const cells = createCreditCells(i);
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
    
    // if (index < debitCount) {
    //   const accountField = document.querySelector(`[name="debits-${index}-account"]`);
    //   const amountField = document.querySelector(`[name="debits-${index}-amount"]`);
    //   const idField = document.querySelector(`[name="debits-${index}-id"]`);
    //   const jeField = document.querySelector(`[name="debits-${index}-journal_entry"]`);
    //   const deleteField = document.querySelector(`[name="debits-${index}-DELETE"]`);
      
    //   if (idField) debitAccountCell.appendChild(idField);
    //   if (jeField) debitAccountCell.appendChild(jeField);
    //   if (accountField) debitAccountCell.appendChild(accountField);
    //   if (amountField) debitAmountCell.appendChild(amountField);
    //   if (deleteField) {
    //     deleteField.style.display = 'none';
    //     debitDeleteCell.appendChild(deleteField);
    //   }
      
    //   const deleteBtn = document.createElement('button');
    //   deleteBtn.type = 'button';
    //   deleteBtn.className = 'btn btn-sm btn-danger remove-debit-button';
    //   deleteBtn.textContent = '削除';
    //   debitDeleteCell.appendChild(deleteBtn);
    // }
    
    // 貸方セル
    const creditAccountCell = document.createElement('td');
    const creditAmountCell = document.createElement('td');
    const creditDeleteCell = document.createElement('td');
    creditDeleteCell.className = 'text-center';
    
    // if (index < creditCount) {
    //   const accountField = document.querySelector(`[name="credits-${index}-account"]`);
    //   const amountField = document.querySelector(`[name="credits-${index}-amount"]`);
    //   const idField = document.querySelector(`[name="credits-${index}-id"]`);
    //   const jeField = document.querySelector(`[name="credits-${index}-journal_entry"]`);
    //   const deleteField = document.querySelector(`[name="credits-${index}-DELETE"]`);
      
    //   if (idField) creditAccountCell.appendChild(idField);
    //   if (jeField) creditAccountCell.appendChild(jeField);
    //   if (accountField) creditAccountCell.appendChild(accountField);
    //   if (amountField) creditAmountCell.appendChild(amountField);
    //   if (deleteField) {
    //     deleteField.style.display = 'none';
    //     creditDeleteCell.appendChild(deleteField);
    //   }
      
    //   const deleteBtn = document.createElement('button');
    //   deleteBtn.type = 'button';
    //   deleteBtn.className = 'btn btn-sm btn-danger remove-credit-button';
    //   deleteBtn.textContent = '削除';
    //   creditDeleteCell.appendChild(deleteBtn);
    // }
    
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
    const { debitAccountCell, debitAmountCell, debitDeleteCell } = createDebitCells(debitFormCount);
    attatchDebitCells(debitAccountCell, debitAmountCell, debitDeleteCell);
    // const newFormHtml = debitTemplate.replace(/__prefix__/g, debitFormCount);
    // const tempDiv = document.createElement('div');
    // tempDiv.innerHTML = newFormHtml;
    
    // const accountField = tempDiv.querySelector('[name*="-account"]');
    // const amountField = tempDiv.querySelector('[name*="-amount"]');
    // const idField = tempDiv.querySelector('[name*="-id"]');
    // const jeField = tempDiv.querySelector('[name*="-journal_entry"]');
    
    // const debitAccountCell = document.createElement('td');
    // const debitAmountCell = document.createElement('td');
    // const debitDeleteCell = document.createElement('td');
    // debitDeleteCell.className = 'text-center';
    
    // if (idField) debitAccountCell.appendChild(idField);
    // if (jeField) debitAccountCell.appendChild(jeField);
    // if (accountField) debitAccountCell.appendChild(accountField);
    // if (amountField) debitAmountCell.appendChild(amountField);
    
    // const deleteCheckbox = document.createElement('input');
    // deleteCheckbox.type = 'checkbox';
    // deleteCheckbox.name = `debits-${debitFormCount}-DELETE`;
    // deleteCheckbox.style.display = 'none';
    // debitDeleteCell.appendChild(deleteCheckbox);
    
    // const deleteBtn = document.createElement('button');
    // deleteBtn.type = 'button';
    // deleteBtn.className = 'btn btn-sm btn-danger remove-debit-button';
    // deleteBtn.textContent = '削除';
    // debitDeleteCell.appendChild(deleteBtn);
    
    // 既存の行を探して借方セルを追加、または新しい行を作成
    // const rows = tbody.querySelectorAll('tr');
    // let inserted = false;
    
    // for (let i = 0; i < rows.length; i++) {
    //   const row = rows[i];
    //   const debitAccount = row.querySelector('td:first-child [name*="debits"][name*="-account"]');
      
    //   if (!debitAccount) {
    //     // この行には借方がないので、借方セルを追加
    //     row.children[0].appendChild(idField || document.createTextNode(''));
    //     if (jeField) row.children[0].appendChild(jeField);
    //     if (accountField) row.children[0].appendChild(accountField);
    //     if (amountField) row.children[1].appendChild(amountField);
    //     row.children[2].appendChild(deleteCheckbox);
    //     row.children[2].appendChild(deleteBtn);
    //     inserted = true;
    //     break;
    //   }
    // }
    
    // // 空きがなければ新しい行を追加
    // if (!inserted) {
    //   const newRow = document.createElement('tr');
    //   newRow.className = 'journal-entry-row';
    //   newRow.appendChild(debitAccountCell);
    //   newRow.appendChild(debitAmountCell);
    //   newRow.appendChild(debitDeleteCell);
    //   newRow.appendChild(document.createElement('td'));
    //   newRow.appendChild(document.createElement('td'));
    //   newRow.appendChild(document.createElement('td'));
    //   tbody.appendChild(newRow);
    // }
    
    debitFormCount++;
    document.querySelector('#id_debits-TOTAL_FORMS').value = debitFormCount;
    
    attachRemoveHandlers();
    updateDeleteButtons();
  });
  
  // 貸方行を追加
  document.getElementById('add-credit-button').addEventListener('click', function () {
    const { creditAccountCell, creditAmountCell, creditDeleteCell } = createCreditCells(creditFormCount);
    attatchCreditCells(creditAccountCell, creditAmountCell, creditDeleteCell);
    
    // 既存の行を探して貸方セルを追加、または新しい行を作成
    // const rows = tbody.querySelectorAll('tr');
    // let inserted = false;
    
    // for (let i = 0; i < rows.length; i++) {
    //   // 行の取得とコンテンツの有無の確認
    //   const row = rows[i];
    //   const creditAccount = row.querySelector('td:nth-child(4) [name*="credits"][name*="-account"]');
      
    //   if (!creditAccount) {
    //     // この行には貸方がないので、貸方セルを追加
    //     row.children[3].appendChild(creditAccountCell);
    //     row.children[4].appendChild(creditAmountCell);
    //     row.children[5].appendChild(creditDeleteCell);
    //     inserted = true;
    //     break;
    //   }
    // }
    
    // // 空きがなければ新しい行を追加
    // if (!inserted) {
    //   const newRow = document.createElement('tr');
    //   newRow.className = 'journal-entry-row';
    //   newRow.appendChild(document.createElement('td'));
    //   newRow.appendChild(document.createElement('td'));
    //   newRow.appendChild(document.createElement('td'));
    //   newRow.appendChild(creditAccountCell);
    //   newRow.appendChild(creditAmountCell);
    //   newRow.appendChild(creditDeleteCell);
    //   tbody.appendChild(newRow);
    // }
    
    creditFormCount++;
    document.querySelector('#id_credits-TOTAL_FORMS').value = creditFormCount;
    
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
        updateDeleteButtons();
      };
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
  const registerCheckbox = document.getElementById('{{ fixed_asset_form.register_as_fixed_asset.id_for_label }}');
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
