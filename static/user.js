/**
 * Smart Gym - Member Portal Controller
 * จัดการระบบ Authentication, ข้อมูลโปรไฟล์, ตารางฝึก AI, การเปลี่ยนรหัสผ่าน, และประวัติการฝึก
 */

let currentUser = null;
let stationsCache = [];
let stationPollInterval = null;

document.addEventListener('DOMContentLoaded', () => {
  checkAuthSession();
  fetchGymStations();
  // อัปเดตสถานะเครื่องเล่นและ Dashboard สมาชิกทุกๆ 4 วินาที (Real-time Sync)
  stationPollInterval = setInterval(() => {
    fetchGymStations();
    if (currentUser && currentUser.user_id) {
      loadUserDashboard(currentUser.user_id);
    }
  }, 4000);
});

/**
 * ตรวจสอบสถานะการล็อกอินจาก localStorage
 */
function checkAuthSession() {
  const savedUserJson = localStorage.getItem('smart_gym_user');
  if (savedUserJson) {
    try {
      currentUser = JSON.parse(savedUserJson);
      renderAuthenticatedView();
      loadUserDashboard(currentUser.user_id);
    } catch (e) {
      localStorage.removeItem('smart_gym_user');
      renderLoginView();
    }
  } else {
    renderLoginView();
  }
}

let regUsernameManuallyEdited = false;

/**
 * สลับแท็บเข้าสู่ระบบ / สมัครสมาชิก
 */
function switchAuthTab(tab) {
  const loginForm = document.getElementById('loginForm');
  const registerForm = document.getElementById('registerForm');
  const tabLoginBtn = document.getElementById('tabLoginBtn');
  const tabRegisterBtn = document.getElementById('tabRegisterBtn');

  if (tab === 'login') {
    loginForm.classList.remove('hidden');
    registerForm.classList.add('hidden');
    tabLoginBtn.className = 'flex-1 py-2 rounded-xl text-xs sm:text-sm font-semibold transition flex items-center justify-center gap-1.5 bg-indigo-600 text-white shadow-md shadow-indigo-600/30';
    tabRegisterBtn.className = 'flex-1 py-2 rounded-xl text-xs sm:text-sm font-semibold transition flex items-center justify-center gap-1.5 text-slate-400 hover:text-slate-200';
  } else {
    loginForm.classList.add('hidden');
    registerForm.classList.remove('hidden');
    tabRegisterBtn.className = 'flex-1 py-2 rounded-xl text-xs sm:text-sm font-semibold transition flex items-center justify-center gap-1.5 bg-indigo-600 text-white shadow-md shadow-indigo-600/30';
    tabLoginBtn.className = 'flex-1 py-2 rounded-xl text-xs sm:text-sm font-semibold transition flex items-center justify-center gap-1.5 text-slate-400 hover:text-slate-200';
  }
}

/**
 * แนะนำ Username อัตโนมัติจากชื่อสมาชิกใหม่
 */
function autoSuggestRegUsername() {
  if (regUsernameManuallyEdited) return;
  const nameVal = document.getElementById('regName').value.trim();
  const usernameInput = document.getElementById('regUsername');
  if (nameVal) {
    usernameInput.value = nameVal.toLowerCase().replace(/\s+/g, '_');
  } else {
    usernameInput.value = '';
  }
}

/**
 * ตรวจจับเมื่อผู้ใช้แก้ไข Username เอง
 */
document.addEventListener('DOMContentLoaded', () => {
  const regUserElem = document.getElementById('regUsername');
  if (regUserElem) {
    regUserElem.addEventListener('input', () => {
      regUsernameManuallyEdited = true;
    });
  }
});

/**
 * สลับหน้าจอเป็นโหมด Login
 */
function renderLoginView() {
  document.getElementById('loginSection').classList.remove('hidden');
  document.getElementById('dashboardSection').classList.add('hidden');
  document.getElementById('navUserArea').innerHTML = `
    <span class="text-xs text-slate-400">กรุณาเข้าสู่ระบบ</span>
  `;
}

/**
 * สลับหน้าจอเป็นโหมด Dashboard
 */
function renderAuthenticatedView() {
  document.getElementById('loginSection').classList.add('hidden');
  document.getElementById('dashboardSection').classList.remove('hidden');
  
  document.getElementById('navUserArea').innerHTML = `
    <div class="flex items-center gap-2 text-xs">
      <span class="text-slate-300 font-medium">👤 ${currentUser.name}</span>
      <button onclick="handleLogout()" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-rose-950/40 text-slate-400 hover:text-rose-300 transition text-[11px] border border-slate-700/60">
        ออก
      </button>
    </div>
  `;
}

/**
 * Helper กรอก Username/Password อัตโนมัติสำหรับทดสอบ
 */
function fillLogin(username, password) {
  switchAuthTab('login');
  document.getElementById('usernameInput').value = username;
  document.getElementById('passwordInput').value = password;
}

/**
 * สลับแสดง/ซ่อนรหัสผ่าน
 */
function togglePasswordVisibility(inputId) {
  const input = document.getElementById(inputId);
  if (!input) return;
  input.type = input.type === 'password' ? 'text' : 'password';
}

/**
 * ฟังก์ชันเข้าสู่ระบบ
 */
async function handleLogin(e) {
  e.preventDefault();
  const username = document.getElementById('usernameInput').value.trim();
  const password = document.getElementById('passwordInput').value;
  const errorBox = document.getElementById('loginErrorMsg');
  const errorText = document.getElementById('loginErrorText');
  const submitBtn = document.getElementById('loginSubmitBtn');

  errorBox.classList.add('hidden');
  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span>กำลังเข้าสู่ระบบ...</span>`;

  try {
    const res = await fetch('/api/user/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'เข้าสู่ระบบไม่สำเร็จ');
    }

    currentUser = data.user;
    localStorage.setItem('smart_gym_user', JSON.stringify(currentUser));
    
    showToast(`ยินดีต้อนรับคุณ ${currentUser.name}! 🎉`, 'success');
    renderAuthenticatedView();
    loadUserDashboard(currentUser.user_id);

  } catch (err) {
    errorText.textContent = err.message;
    errorBox.classList.remove('hidden');
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<span>เข้าสู่ระบบ</span><span>➔</span>`;
  }
}

/**
 * ฟังก์ชันสมัครสมาชิกใหม่โดยตรง (User Self-Service)
 */
async function handleRegister(e) {
  e.preventDefault();
  const name = document.getElementById('regName').value.trim();
  const username = document.getElementById('regUsername').value.trim().toLowerCase();
  const password = document.getElementById('regPassword').value;
  const confirmPassword = document.getElementById('regConfirmPassword').value;
  const gender = document.getElementById('regGender').value;
  const fitnessLevel = document.getElementById('regFitnessLevel').value;
  const targetGoal = document.getElementById('regTargetGoal').value.trim();
  const injuryNote = document.getElementById('regInjuryNote').value.trim();

  const errorBox = document.getElementById('registerErrorMsg');
  const errorText = document.getElementById('registerErrorText');
  const submitBtn = document.getElementById('registerSubmitBtn');

  errorBox.classList.add('hidden');

  if (password !== confirmPassword) {
    errorText.textContent = 'รหัสผ่านและการยืนยันรหัสผ่านไม่ตรงกัน';
    errorBox.classList.remove('hidden');
    return;
  }

  if (password.length < 4) {
    errorText.textContent = 'รหัสผ่านต้องมีความยาวอย่างน้อย 4 ตัวอักษร';
    errorBox.classList.remove('hidden');
    return;
  }

  if (username.length < 3) {
    errorText.textContent = 'ชื่อผู้ใช้ (Username) ต้องมีความยาวอย่างน้อย 3 ตัวอักษร';
    errorBox.classList.remove('hidden');
    return;
  }

  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span>กำลังสร้างบัญชีสมาชิก...</span>`;

  try {
    const res = await fetch('/api/user/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        username,
        password,
        gender,
        fitness_level: fitnessLevel,
        target_goal: targetGoal,
        injury_note: injuryNote || null
      })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'สมัครสมาชิกไม่สำเร็จ');
    }

    currentUser = data.user;
    localStorage.setItem('smart_gym_user', JSON.stringify(currentUser));

    showToast(`ยินดีต้อนรับสมาชิกใหม่คุณ ${currentUser.name}! 🎉`, 'success');
    renderAuthenticatedView();
    loadUserDashboard(currentUser.user_id);

  } catch (err) {
    errorText.textContent = err.message;
    errorBox.classList.remove('hidden');
  } finally {
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<span>📝 สมัครสมาชิกทันที</span><span>➔</span>`;
  }
}

/**
 * ออกจากระบบ
 */
function handleLogout() {
  if (confirm('ต้องการออกจากระบบหรือไม่?')) {
    localStorage.removeItem('smart_gym_user');
    currentUser = null;
    renderLoginView();
    showToast('ออกจากระบบเรียบร้อยแล้ว', 'info');
  }
}

/**
 * ดึงข้อมูลภาพรวมของผู้ใช้ (Summary, AI routines, ประวัติการฝึก)
 */
async function loadUserDashboard(userId) {
  try {
    const res = await fetch(`/api/user/${userId}/summary`);
    if (!res.ok) throw new Error('Failed to load user summary');
    const summary = await res.json();

    const user = summary.user;
    currentUser = user; // อัปเดตข้อมูลล่าสุด

    // 1. อัปเดตข้อมูลโปรไฟล์ส่วนตัว
    document.getElementById('profileName').textContent = user.name;
    document.getElementById('profileUsername').textContent = user.username ? `@${user.username}` : '';
    document.getElementById('profileFitnessLevel').textContent = `⚡ ระดับ: ${user.fitness_level || 'Beginner'}`;
    document.getElementById('profileTargetGoal').textContent = `🎯 เป้าหมาย: ${user.target_goal || '-'}`;

    // ตรวจสอบสถานะการผูกบัตร NFC
    const isPendingCard = !user.nfc_uid || user.nfc_uid.startsWith('PENDING_');
    const nfcUidElem = document.getElementById('profileNfcUid');
    const pendingNoticeElem = document.getElementById('pendingCardNotice');

    if (isPendingCard) {
      nfcUidElem.innerHTML = `<span class="text-amber-400 font-semibold">NFC_ID: ⚠️ รอผูกบัตร</span>`;
      if (pendingNoticeElem) pendingNoticeElem.classList.remove('hidden');
    } else {
      nfcUidElem.textContent = `NFC_ID: ${user.nfc_uid}`;
      if (pendingNoticeElem) pendingNoticeElem.classList.add('hidden');
    }

    // ข้อจำกัดทางร่างกาย / ประวัติการบาดเจ็บ
    const injuryBanner = document.getElementById('injuryBanner');
    const injuryText = document.getElementById('injuryNoteText');
    if (user.injury_note && user.injury_note.trim() !== '') {
      injuryText.textContent = user.injury_note;
      injuryBanner.classList.remove('hidden');
    } else {
      injuryBanner.classList.add('hidden');
    }

    // 2. แสดงตารางฝึกจาก AI วันนี้
    renderAiRoutines(summary.today_routines);

    // 3. แสดงประวัติการฝึกย้อนหลัง
    renderWorkoutHistory(summary.recent_history, summary.total_workouts);

  } catch (err) {
    console.error('Error loading dashboard:', err);
    showToast('เกิดข้อผิดพลาดในการโหลดข้อมูลโปรไฟล์', 'error');
  }
}

/**
 * แสดงตารางฝึกที่ AI เจนให้
 */
function renderAiRoutines(routines) {
  const container = document.getElementById('aiRoutineList');
  if (!routines || routines.length === 0) {
    container.innerHTML = `
      <div class="p-6 rounded-2xl bg-slate-800/50 border border-slate-700/60 text-center">
        <div class="text-3xl mb-2">💡</div>
        <p class="text-sm font-semibold text-slate-300">ยังไม่มีตารางฝึกที่บันทึกไว้ในวันนี้</p>
        <p class="text-xs text-slate-400 mt-1 max-w-md mx-auto">
          เมื่อคุณนำบัตร NFC ไปแตะที่เครื่องเล่นในยิม หรือกดปุ่มด้านล่างเพื่อสร้างแผนการฝึกจาก Gemini AI ได้ทันที
        </p>
        <button 
          type="button" 
          onclick="requestAiRoutineFromWeb()" 
          id="btnGenAiRoutine"
          class="mt-4 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-lg shadow-indigo-600/30 transition inline-flex items-center gap-1.5"
        >
          <span>🤖</span>
          <span>สร้างคำแนะนำจาก AI ทันที</span>
        </button>
      </div>
    `;
    return;
  }

  container.innerHTML = routines.map((r) => {
    let planData = {};
    try {
      planData = typeof r.ai_response_json === 'string' ? JSON.parse(r.ai_response_json) : r.ai_response_json;
    } catch (e) {
      planData = { exercise: r.station_name, target: '3 Sets x 10-12 Reps', weight: 'Moderate', tip: '-' };
    }

    return `
      <div class="p-5 rounded-2xl bg-gradient-to-br from-indigo-950/30 via-slate-800/80 to-slate-900 border border-indigo-500/20 shadow-lg relative overflow-hidden">
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <span class="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center text-sm font-bold">
              🏋️
            </span>
            <div>
              <h4 class="font-bold text-white text-sm sm:text-base">${r.station_name}</h4>
              <p class="text-[11px] text-slate-400">โฟกัส: ${r.target_muscles || 'Full Body'}</p>
            </div>
          </div>
          <span class="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400">
            ${r.routine_date}
          </span>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5 my-3">
          <div class="bg-slate-900/60 rounded-xl p-3 border border-slate-800">
            <span class="text-[10px] text-slate-400 uppercase tracking-wider block">ท่าฝึก (Exercise)</span>
            <span class="font-semibold text-indigo-200 text-xs sm:text-sm">${planData.exercise || r.station_name}</span>
          </div>
          <div class="bg-slate-900/60 rounded-xl p-3 border border-slate-800">
            <span class="text-[10px] text-slate-400 uppercase tracking-wider block">เป้าหมาย (Sets x Reps)</span>
            <span class="font-bold text-emerald-400 text-xs sm:text-sm">${planData.target || '3 x 10'}</span>
          </div>
          <div class="bg-slate-900/60 rounded-xl p-3 border border-slate-800">
            <span class="text-[10px] text-slate-400 uppercase tracking-wider block">น้ำหนักแนะนำ (Weight)</span>
            <span class="font-bold text-amber-300 text-xs sm:text-sm">${planData.weight || 'ตามความเหมาะสม'}</span>
          </div>
        </div>

        ${planData.tip ? `
          <div class="mt-2.5 p-3 rounded-xl bg-indigo-950/40 border border-indigo-500/20 text-xs text-indigo-200 flex items-start gap-2">
            <span class="text-sm">💡</span>
            <div>
              <span class="font-semibold text-indigo-300">AI Safety Cue:</span>
              <span class="text-slate-300">${planData.tip}</span>
            </div>
          </div>
        ` : ''}
      </div>
    `;
  }).join('');
}

/**
 * ขอคำแนะนำจาก AI ผ่านหน้าเว็บโดยตรง
 */
async function requestAiRoutineFromWeb() {
  if (!currentUser || !currentUser.user_id) return;
  const selectElem = document.getElementById('logStationSelect');
  const stationId = selectElem && selectElem.value ? selectElem.value : (stationsCache[0] ? stationsCache[0].station_id : 'STATION_CHEST_PRESS');
  const btn = document.getElementById('btnGenAiRoutine');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span><span>กำลังวิเคราะห์แผนการฝึก...</span>';
  }
  try {
    const res = await fetch('/api/user/generate-routine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: currentUser.user_id, station_id: stationId })
    });
    if (!res.ok) throw new Error('ไม่สามารถสร้างแผนการฝึกได้');
    showToast('สร้างแผนการฝึกจาก AI เรียบร้อย! 🎉', 'success');
    await loadUserDashboard(currentUser.user_id);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<span>🤖</span><span>สร้างคำแนะนำจาก AI ทันที</span>';
    }
  }
}

/**
 * แสดงประวัติการฝึกย้อนหลัง
 */
function renderWorkoutHistory(history, totalCount) {
  const container = document.getElementById('workoutHistoryList');
  const countBadge = document.getElementById('totalWorkoutBadge');
  if (countBadge) countBadge.textContent = `${totalCount || 0} ครั้ง`;

  if (!history || history.length === 0) {
    container.innerHTML = `
      <p class="text-xs text-slate-500 text-center py-6">ยังไม่มีประวัติการฝึกที่บันทึกไว้</p>
    `;
    return;
  }

  container.innerHTML = history.map((item) => `
    <div class="p-3.5 rounded-xl bg-slate-800/60 border border-slate-700/60 flex items-center justify-between text-xs sm:text-sm">
      <div class="flex items-center gap-3">
        <div class="w-9 h-9 rounded-xl bg-slate-700/50 flex items-center justify-center text-base">
          💪
        </div>
        <div>
          <p class="font-semibold text-white">${item.exercise_name || item.station_name || 'Workout Session'}</p>
          <p class="text-[11px] text-slate-400 font-mono">${item.timestamp || '-'}</p>
        </div>
      </div>
      <div class="text-right">
        <span class="font-bold text-emerald-400 font-mono text-sm">${item.weight_kg} kg</span>
        <p class="text-[11px] text-slate-400">${item.sets_completed} เซ็ต × ${item.reps_completed} เรป</p>
      </div>
    </div>
  `).join('');
}

/**
 * ดึงสถานะเครื่องเล่นในยิมแบบสด
 */
async function fetchGymStations() {
  try {
    const res = await fetch('/api/stations');
    if (!res.ok) return;
    const stations = await res.json();
    stationsCache = stations;

    // อัปเดต Dropdown ในฟอร์มบันทึกผลการเล่น
    const selectElem = document.getElementById('logStationSelect');
    if (selectElem && selectElem.options.length <= 1) {
      selectElem.innerHTML = stations.map(s => `
        <option value="${s.station_id}">${s.station_name}</option>
      `).join('');
    }

    // แสดงผล Widget สถานะเครื่องเล่น
    const widgetContainer = document.getElementById('gymStationsWidgetList');
    if (!widgetContainer) return;

    widgetContainer.innerHTML = stations.map(s => {
      const isIdle = s.status === 'idle';
      return `
        <div class="p-3 rounded-2xl ${isIdle ? 'bg-slate-800/40 border-slate-700/50' : 'bg-rose-950/20 border-rose-900/40'} border flex items-center justify-between text-xs transition">
          <div>
            <p class="font-medium text-slate-200 text-xs">${s.station_name}</p>
            <p class="text-[10px] text-slate-400 font-mono">${s.target_muscles}</p>
          </div>
          <div>
            ${isIdle ? `
              <span class="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] font-medium flex items-center gap-1">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> ว่าง
              </span>
            ` : `
              <span class="px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20 text-[10px] font-medium flex items-center gap-1">
                <span class="w-1.5 h-1.5 rounded-full bg-rose-400 animate-pulse"></span> กำลังใช้
              </span>
            `}
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    console.error('Failed to fetch stations:', err);
  }
}

/**
 * จัดการบันทึกผลการออกกำลังกายจริง
 */
async function handleLogWorkout(e) {
  e.preventDefault();
  if (!currentUser) return;

  const stationId = document.getElementById('logStationSelect').value;
  const exerciseName = document.getElementById('logExerciseInput').value.trim();
  const weightKg = parseFloat(document.getElementById('logWeightInput').value);
  const sets = parseInt(document.getElementById('logSetsInput').value);
  const reps = parseInt(document.getElementById('logRepsInput').value);

  try {
    const res = await fetch('/api/user/log-workout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: currentUser.user_id,
        station_id: stationId,
        exercise_name: exerciseName,
        weight_kg: weightKg,
        sets: sets,
        reps: reps
      })
    });

    if (!res.ok) throw new Error('บันทึกผลการออกกำลังกายไม่สำเร็จ');

    showToast(`บันทึก ${exerciseName} (${weightKg} kg) สำเร็จ! 🔥`, 'success');
    document.getElementById('logWorkoutForm').reset();
    // โหลดข้อมูล Dashboard ใหม่
    loadUserDashboard(currentUser.user_id);

  } catch (err) {
    showToast(err.message, 'error');
  }
}

/**
 * Modal จัดการเปลี่ยนรหัสผ่าน
 */
function openPasswordModal() {
  document.getElementById('passwordModal').classList.remove('hidden');
  document.getElementById('passwordModalError').classList.add('hidden');
  document.getElementById('changePasswordForm').reset();
}

function closePasswordModal() {
  document.getElementById('passwordModal').classList.add('hidden');
}

async function handleChangePassword(e) {
  e.preventDefault();
  if (!currentUser) return;

  const oldPassword = document.getElementById('oldPasswordInput').value;
  const newPassword = document.getElementById('newPasswordInput').value;
  const confirmPassword = document.getElementById('confirmPasswordInput').value;
  const errorBox = document.getElementById('passwordModalError');
  const saveBtn = document.getElementById('savePasswordBtn');

  if (newPassword !== confirmPassword) {
    errorBox.textContent = 'รหัสผ่านใหม่และการยืนยันรหัสผ่านไม่ตรงกัน';
    errorBox.classList.remove('hidden');
    return;
  }

  if (newPassword.length < 4) {
    errorBox.textContent = 'รหัสผ่านใหม่ต้องมีความยาวอย่างน้อย 4 ตัวอักษร';
    errorBox.classList.remove('hidden');
    return;
  }

  saveBtn.disabled = true;
  saveBtn.textContent = 'กำลังบันทึก...';
  errorBox.classList.add('hidden');

  try {
    const res = await fetch('/api/user/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: currentUser.user_id,
        old_password: oldPassword,
        new_password: newPassword
      })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'เปลี่ยนรหัสผ่านไม่สำเร็จ');
    }

    showToast('เปลี่ยนรหัสผ่านสำเร็จแล้ว! 🔐', 'success');
    closePasswordModal();

  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.classList.remove('hidden');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = 'บันทึกรหัสผ่านใหม่';
  }
}

/**
 * Toast Notification Utility
 */
function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  const bgColors = {
    success: 'bg-emerald-950/90 border-emerald-500/40 text-emerald-200',
    error: 'bg-rose-950/90 border-rose-500/40 text-rose-200',
    info: 'bg-indigo-950/90 border-indigo-500/40 text-indigo-200'
  };

  const icons = {
    success: '✅',
    error: '❌',
    info: 'ℹ️'
  };

  toast.className = `toast pointer-events-auto flex items-center gap-2.5 px-4 py-3 rounded-2xl border shadow-xl backdrop-blur-md text-xs sm:text-sm ${bgColors[type] || bgColors.info}`;
  toast.innerHTML = `
    <span>${icons[type] || 'ℹ️'}</span>
    <span class="font-medium">${message}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('hiding');
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
