let allUsers = [];
let isScanning = false;
let abortScanController = null;
let usernameManuallyChanged = false;

// โหลดรายชื่อผู้ใช้เมื่อเปิดหน้าเว็บ
document.addEventListener('DOMContentLoaded', () => {
  fetchUsers();
});

// ดึงข้อมูลผู้ใช้ทั้งหมด
async function fetchUsers() {
  try {
    const res = await fetch('/api/users');
    allUsers = await res.json();
    renderTable(allUsers);
  } catch (err) {
    alert('Failed to load user list');
  }
}

// แนะนำ Username อัตโนมัติจากชื่อ
function autoSuggestUsername() {
  if (usernameManuallyChanged) return;
  const nameVal = document.getElementById('name').value.trim();
  const usernameInput = document.getElementById('username');
  if (nameVal) {
    usernameInput.value = nameVal.toLowerCase().replace(/\s+/g, '_');
  } else {
    usernameInput.value = '';
  }
}

function onUsernameInput() {
  usernameManuallyChanged = true;
}

// เรนเดอร์ข้อมูลลงในตาราง
function renderTable(users) {
  const tbody = document.getElementById('userTableBody');
  tbody.innerHTML = '';

  if (users.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-slate-500">No members registered yet</td></tr>`;
    return;
  }

  users.forEach(u => {
    const tr = document.createElement('tr');
    tr.className = "hover:bg-slate-700/40 border-b border-slate-700 transition";
    
    // ตรวจสอบสถานะบัตร NFC
    const isPending = !u.nfc_uid || u.nfc_uid.startsWith('PENDING_');
    const nfcDisplay = isPending 
      ? `<span class="px-2 py-0.5 rounded text-xs bg-amber-500/10 text-amber-300 border border-amber-500/30 flex items-center gap-1 w-fit">⚠️ รอแตะผูกบัตร</span>`
      : `<span class="font-mono text-blue-400 font-semibold">${u.nfc_uid}</span>`;

    tr.innerHTML = `
      <td class="py-3 px-3 font-mono text-slate-400">#${u.user_id}</td>
      <td class="py-3 px-3">${nfcDisplay}</td>
      <td class="py-3 px-3">
        <div class="font-medium text-slate-100">${u.name}</div>
        <div class="text-[11px] text-slate-400 font-mono">@${u.username || '-'}</div>
      </td>
      <td class="py-3 px-3"><span class="px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-300">${u.fitness_level}</span></td>
      <td class="py-3 px-3 text-slate-300">${u.target_goal}</td>
      <td class="py-3 px-3 text-right space-x-1 sm:space-x-2">
        ${isPending ? `
          <button onclick="bindNfcCard(${u.user_id})" class="px-2.5 py-1 bg-indigo-600/30 text-indigo-300 hover:bg-indigo-600/50 rounded text-xs transition">
            🔗 ผูกบัตร
          </button>
        ` : ''}
        <button onclick="editUser(${u.user_id})" class="px-2.5 py-1 bg-amber-600/30 text-amber-400 hover:bg-amber-600/50 rounded text-xs transition">Edit</button>
        <button onclick="deleteUser(${u.user_id})" class="px-2.5 py-1 bg-red-600/30 text-red-400 hover:bg-red-600/50 rounded text-xs transition">Delete</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// ค้นหาสมาชิก
function filterUsers() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  const filtered = allUsers.filter(u => 
    u.name.toLowerCase().includes(q) || 
    (u.nfc_uid && u.nfc_uid.toLowerCase().includes(q)) ||
    (u.username && u.username.toLowerCase().includes(q))
  );
  renderTable(filtered);
}

// ดึงข้อมูลขึ้นมาแก้ไข
function editUser(userId) {
  const user = allUsers.find(u => u.user_id === userId);
  if (!user) return;

  usernameManuallyChanged = true;
  document.getElementById('userId').value = user.user_id;
  document.getElementById('nfcUid').value = user.nfc_uid && !user.nfc_uid.startsWith('PENDING_') ? user.nfc_uid : '';
  document.getElementById('name').value = user.name;
  document.getElementById('username').value = user.username || '';
  document.getElementById('password').value = '';
  document.getElementById('password').placeholder = 'เว้นว่างไว้หากไม่เปลี่ยน';
  document.getElementById('gender').value = user.gender || 'Male';
  document.getElementById('fitnessLevel').value = user.fitness_level;
  document.getElementById('targetGoal').value = user.target_goal;
  document.getElementById('injuryNote').value = user.injury_note || '';

  document.getElementById('formTitle').innerText = `✏️ Edit Member (#${user.user_id})`;
  document.getElementById('submitBtn').innerText = 'Update Member';
  document.getElementById('submitBtn').className = 'w-full bg-amber-600 hover:bg-amber-500 text-white font-semibold py-2 rounded-lg text-sm transition';
  
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ปุ่มลัดสำหรับผูกบัตรให้สมาชิกที่รอผูกบัตร
function bindNfcCard(userId) {
  editUser(userId);
  const nfcInput = document.getElementById('nfcUid');
  nfcInput.focus();
  if (!isScanning) {
    toggleScanMode();
  }
}

// รีเซ็ตฟอร์ม
function resetForm() {
  document.getElementById('userForm').reset();
  document.getElementById('userId').value = '';
  document.getElementById('password').value = '1234';
  document.getElementById('password').placeholder = 'Default: 1234';
  usernameManuallyChanged = false;
  document.getElementById('formTitle').innerText = '➕ Add New Member';
  document.getElementById('submitBtn').innerText = 'Save Member';
  document.getElementById('submitBtn').className = 'w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2 rounded-lg text-sm transition';
  stopScanning();
}

// ส่งฟอร์มบันทึก/แก้ไข
async function handleFormSubmit(e) {
  e.preventDefault();
  const userId = document.getElementById('userId').value;
  const nfcVal = document.getElementById('nfcUid').value.trim().toUpperCase();
  const passwordVal = document.getElementById('password').value;

  const payload = {
    nfc_uid: nfcVal || null,
    name: document.getElementById('name').value.trim(),
    username: document.getElementById('username').value.trim().toLowerCase() || null,
    password: passwordVal.trim() || null,
    gender: document.getElementById('gender').value,
    fitness_level: document.getElementById('fitnessLevel').value,
    target_goal: document.getElementById('targetGoal').value.trim(),
    injury_note: document.getElementById('injuryNote').value.trim() || null
  };

  try {
    const url = userId ? `/api/users/${userId}` : '/api/users';
    const method = userId ? 'PUT' : 'POST';

    const res = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || 'Failed to save member');
      return;
    }

    alert(userId ? 'Updated member successfully!' : 'Added new member successfully!');
    resetForm();
    fetchUsers();
  } catch (err) {
    alert('Network error occurred.');
  }
}

// ลบสมาชิก
async function deleteUser(userId) {
  if (!confirm(`Are you sure you want to delete member #${userId}?`)) return;

  try {
    const res = await fetch(`/api/users/${userId}`, { method: 'DELETE' });
    if (!res.ok) {
      alert('Failed to delete member');
      return;
    }
    fetchUsers();
  } catch (err) {
    alert('Network error occurred.');
  }
}

// สลับโหมดสแกนบัตร USB PN532
function toggleScanMode() {
  if (isScanning) {
    stopScanning();
  } else {
    startScanning();
  }
}

async function startScanning() {
  isScanning = true;
  const scanBtn = document.getElementById('scanBtn');
  const scanText = document.getElementById('scanText');
  const scanBadge = document.getElementById('scanBadge');
  const nfcInput = document.getElementById('nfcUid');

  if (scanBtn) {
    scanBtn.className = 'text-xs px-2.5 py-1 bg-amber-600 hover:bg-amber-500 text-white rounded font-medium transition flex items-center gap-1 animate-pulse';
    scanText.innerText = 'Listening for Card...';
  }
  if (scanBadge) {
    scanBadge.innerText = 'Tap NFC card now... (6s)';
    scanBadge.classList.remove('hidden');
  }
  if (nfcInput) {
    nfcInput.placeholder = 'Scanning for USB PN532...';
  }

  abortScanController = new AbortController();

  try {
    const res = await fetch('/api/trigger-scan', {
      method: 'POST',
      signal: abortScanController.signal
    });

    const data = await res.json();

    if (data.status === 'success' && data.nfc_uid) {
      nfcInput.value = data.nfc_uid;
      nfcInput.classList.add('border-emerald-500', 'bg-emerald-950/30');
      setTimeout(() => {
        nfcInput.classList.remove('border-emerald-500', 'bg-emerald-950/30');
      }, 2000);
    } else {
      nfcInput.placeholder = 'Timeout (No card tapped). Try again.';
    }
  } catch (err) {
    if (err.name !== 'AbortError') {
      console.error('[NFC Scan Error]:', err);
      nfcInput.placeholder = 'Connection error. Check server.';
    }
  } finally {
    stopScanning();
  }
}

function stopScanning() {
  isScanning = false;
  const scanBtn = document.getElementById('scanBtn');
  const scanText = document.getElementById('scanText');
  const scanBadge = document.getElementById('scanBadge');
  const nfcInput = document.getElementById('nfcUid');

  if (abortScanController) {
    try { abortScanController.abort(); } catch (e) {}
    abortScanController = null;
  }

  if (scanBtn) {
    scanBtn.className = 'text-xs px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium transition flex items-center gap-1';
    scanText.innerText = 'Scan from PN532';
  }
  if (scanBadge) scanBadge.classList.add('hidden');
  if (nfcInput && !nfcInput.value) {
    nfcInput.placeholder = 'e.g. 0498943BC82A81 (หรือเว้นว่างไว้)';
  }
}