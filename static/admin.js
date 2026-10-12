let allUsers = [];
let isScanning = false;
let abortScanController = null;

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
    tr.innerHTML = `
      <td class="py-3 px-3 font-mono text-slate-400">#${u.user_id}</td>
      <td class="py-3 px-3 font-mono text-blue-400 font-semibold">${u.nfc_uid}</td>
      <td class="py-3 px-3 font-medium text-slate-100">${u.name}</td>
      <td class="py-3 px-3"><span class="px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-300">${u.fitness_level}</span></td>
      <td class="py-3 px-3 text-slate-300">${u.target_goal}</td>
      <td class="py-3 px-3 text-right space-x-2">
        <button onclick="editUser(${u.user_id})" class="px-2.5 py-1 bg-amber-600/30 text-amber-400 hover:bg-amber-600/50 rounded text-xs transition">Edit</button>
        <button onclick="deleteUser(${u.user_id})" class="px-2.5 py-1 bg-red-600/30 text-red-400 hover:bg-red-600/50 rounded text-xs transition">Delete</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// ค้นหาตามชื่อหรือ UID
function filterUsers() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  const filtered = allUsers.filter(u => 
    u.name.toLowerCase().includes(q) || u.nfc_uid.toLowerCase().includes(q)
  );
  renderTable(filtered);
}

// เตรียมข้อมูลฟอร์มเพื่อแก้ไข
function editUser(userId) {
  const user = allUsers.find(u => u.user_id === userId);
  if (!user) return;

  document.getElementById('userId').value = user.user_id;
  document.getElementById('nfcUid').value = user.nfc_uid;
  document.getElementById('name').value = user.name;
  document.getElementById('gender').value = user.gender || 'Male';
  document.getElementById('fitnessLevel').value = user.fitness_level;
  document.getElementById('targetGoal').value = user.target_goal;
  document.getElementById('injuryNote').value = user.injury_note || '';

  document.getElementById('formTitle').innerText = `✏️ Edit Member (#${user.user_id})`;
  const submitBtn = document.getElementById('submitBtn');
  submitBtn.innerText = 'Update Member';
  submitBtn.className = 'w-full bg-amber-600 hover:bg-amber-500 text-white font-semibold py-2 rounded-lg text-sm transition';
}

// รีเซ็ตฟอร์ม
function resetForm() {
  document.getElementById('userForm').reset();
  document.getElementById('userId').value = '';
  document.getElementById('formTitle').innerText = '➕ Add New Member';
  const submitBtn = document.getElementById('submitBtn');
  submitBtn.innerText = 'Save Member';
  submitBtn.className = 'w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2 rounded-lg text-sm transition';
  stopScanningUI();
}

// บันทึกข้อมูลสมาชิก (เพิ่มใหม่ หรือ อัปเดต)
async function handleFormSubmit(e) {
  e.preventDefault();
  const userId = document.getElementById('userId').value;
  const payload = {
    nfc_uid: document.getElementById('nfcUid').value.trim().toUpperCase(),
    name: document.getElementById('name').value.trim(),
    gender: document.getElementById('gender').value,
    fitness_level: document.getElementById('fitnessLevel').value,
    target_goal: document.getElementById('targetGoal').value.trim(),
    injury_note: document.getElementById('injuryNote').value.trim() || null
  };

  try {
    let res;
    if (userId) {
      res = await fetch(`/api/users/${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } else {
      res = await fetch('/api/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    }

    if (!res.ok) {
      const data = await res.json();
      alert('Error: ' + data.detail);
      return;
    }

    resetForm();
    fetchUsers();
  } catch (err) {
    alert('Network request failed');
  }
}

// ลบสมาชิก
async function deleteUser(userId) {
  if (!confirm(`Are you sure you want to delete member #${userId}?`)) return;
  try {
    const res = await fetch(`/api/users/${userId}`, { method: 'DELETE' });
    if (res.ok) {
      fetchUsers();
      resetForm();
    } else {
      alert('Failed to delete member');
    }
  } catch (err) {
    alert('Network error');
  }
}

// ---------------- LIVE NFC SCANNING ----------------
async function toggleScanMode() {
  const scanBtn = document.getElementById('scanBtn');
  const scanText = document.getElementById('scanText');
  const scanBadge = document.getElementById('scanBadge');
  const nfcInput = document.getElementById('nfcUid');

  if (isScanning) {
    if (abortScanController) abortScanController.abort();
    stopScanningUI();
    return;
  }

  isScanning = true;
  abortScanController = new AbortController();

  nfcInput.value = '';
  nfcInput.placeholder = 'Tap card on PN532 now...';
  scanBtn.className = 'text-xs px-2.5 py-1 bg-rose-600 hover:bg-rose-500 text-white rounded font-medium transition flex items-center gap-1';
  scanText.innerText = 'Cancel';
  scanBadge.classList.remove('hidden');

  try {
    const res = await fetch('/api/trigger-scan', {
      method: 'POST',
      signal: abortScanController.signal
    });
    const data = await res.json();
    console.log('[NFC Scan Result]:', data);

    if (data.debug && data.debug.connected_port) {
      console.info(`[NFC] Connected to port: ${data.debug.connected_port} (${data.debug.baudrate} baud)`);
    }

    if (data.status === 'success' && data.nfc_uid) {
      nfcInput.value = data.nfc_uid;
      nfcInput.classList.add('border-emerald-500', 'bg-emerald-950/30');
      setTimeout(() => {
        nfcInput.classList.remove('border-emerald-500', 'bg-emerald-950/30');
      }, 1500);
    } else {
      const portMsg = data.debug && data.debug.connected_port ? ` on ${data.debug.connected_port}` : '';
      nfcInput.placeholder = `Scan timeout${portMsg}. Please try again.`;
    }
  } catch (err) {
    if (err.name !== 'AbortError') {
      console.error(err);
    }
  } finally {
    stopScanningUI();
  }

}

function stopScanningUI() {
  isScanning = false;
  const scanBtn = document.getElementById('scanBtn');
  const scanText = document.getElementById('scanText');
  const scanBadge = document.getElementById('scanBadge');
  const nfcInput = document.getElementById('nfcUid');

  if (scanBtn) {
    scanBtn.className = 'text-xs px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded font-medium transition flex items-center gap-1';
    scanText.innerText = 'Scan from PN532';
  }
  if (scanBadge) scanBadge.classList.add('hidden');
  if (nfcInput && !nfcInput.value) {
    nfcInput.placeholder = 'e.g. 0498943BC82A81';
  }
}