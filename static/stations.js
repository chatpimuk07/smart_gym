/**
 * Smart Gym - Station Live Status Controller
 * จัดการการดึงข้อมูลสถานะเครื่องเล่น การกรองข้อมูล และการรีเซ็ตสถานะแบบ Real-time
 */

let stationsData = [];
let currentFilter = 'all';
let autoRefreshInterval = null;

// เริ่มทำงานเมื่อ DOM พร้อมใช้งาน
document.addEventListener('DOMContentLoaded', () => {
  fetchStations();
  // Auto-refresh ทุกๆ 3 วินาที เพื่อดูสถานะเรียลไทม์
  autoRefreshInterval = setInterval(fetchStations, 3000);
});

/**
 * ดึงข้อมูลสถานะเครื่องเล่นทั้งหมดจาก REST API
 */
async function fetchStations() {
  try {
    const res = await fetch('/api/stations');
    if (!res.ok) throw new Error('API Error');
    stationsData = await res.json();
    updateCounters();
    renderStations();
    const lastUpdatedElem = document.getElementById('lastUpdatedTime');
    if (lastUpdatedElem) {
      lastUpdatedElem.textContent = `(อัปเดตล่าสุด: ${new Date().toLocaleTimeString('th-TH')})`;
    }
  } catch (err) {
    console.error('Failed to fetch stations:', err);
  }
}

/**
 * อัปเดตตัวเลขสถิติสรุปบนการ์ดด้านบน
 */
function updateCounters() {
  const total = stationsData.length;
  const idle = stationsData.filter(s => s.status === 'idle').length;
  const inUse = stationsData.filter(s => s.status === 'in_use').length;

  const totalElem = document.getElementById('totalCount');
  const availableElem = document.getElementById('availableCount');
  const inUseElem = document.getElementById('inUseCount');

  if (totalElem) totalElem.textContent = total;
  if (availableElem) availableElem.textContent = idle;
  if (inUseElem) inUseElem.textContent = inUse;
}

/**
 * เปลี่ยนตัวกรองสถานะ (all / idle / in_use)
 */
function setFilter(filter) {
  currentFilter = filter;
  ['all', 'idle', 'in_use'].forEach(f => {
    const btn = document.getElementById(`filter-${f}`);
    if (btn) {
      if (f === filter) {
        btn.className = 'px-3.5 py-1.5 rounded-lg text-xs font-semibold transition bg-blue-600 text-white';
      } else {
        btn.className = 'px-3.5 py-1.5 rounded-lg text-xs font-semibold transition text-slate-300 hover:text-white';
      }
    }
  });
  renderStations();
}

/**
 * แสดงผลการ์ดสถานะของแต่ละ Station ตามตัวกรองและคำค้นหา
 */
function renderStations() {
  const container = document.getElementById('stationsGrid');
  if (!container) return;

  const searchInput = document.getElementById('searchInput');
  const searchQuery = (searchInput ? searchInput.value : '').toLowerCase().trim();

  const filtered = stationsData.filter(station => {
    const matchesFilter = (currentFilter === 'all') || (station.status === currentFilter);
    const nameMatch = (station.station_name || '').toLowerCase().includes(searchQuery);
    const idMatch = (station.station_id || '').toLowerCase().includes(searchQuery);
    const muscleMatch = (station.target_muscles || '').toLowerCase().includes(searchQuery);
    const userMatch = (station.current_user_name || '').toLowerCase().includes(searchQuery);
    return matchesFilter && (nameMatch || idMatch || muscleMatch || userMatch);
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="col-span-full py-16 text-center bg-slate-800/40 rounded-2xl border border-slate-800">
        <span class="text-4xl block mb-2">🔍</span>
        <p class="text-slate-400 font-medium">ไม่พบเครื่องเล่นที่ตรงตามเงื่อนไข</p>
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(station => {
    const isIdle = (station.status === 'idle');
    const muscleBadges = (station.target_muscles || '')
      .split(',')
      .map(m => m.trim())
      .filter(m => m.length > 0)
      .map(m => `<span class="bg-slate-900/80 text-slate-300 border border-slate-700/80 px-2 py-0.5 rounded text-[11px]">${m}</span>`)
      .join('');

    return `
      <div class="station-card rounded-2xl border transition-all duration-300 shadow-lg flex flex-col justify-between overflow-hidden ${
        isIdle 
          ? 'bg-slate-800/90 border-slate-700 hover:border-emerald-500/50 status-idle-glow' 
          : 'bg-slate-800/95 border-rose-900/60 status-in-use-glow'
      }">
        
        <!-- Top Status Bar & Header -->
        <div>
          <div class="px-5 pt-5 pb-4 border-b border-slate-700/60">
            <div class="flex items-start justify-between gap-3">
              <div class="flex-1">
                <span class="font-mono text-[11px] font-semibold text-slate-400 tracking-wider uppercase block mb-1">
                  ${station.station_id}
                </span>
                <h3 class="text-lg font-bold text-white leading-snug">
                  ${station.station_name}
                </h3>
              </div>

              <!-- Status Pill -->
              <div>
                ${isIdle ? `
                  <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 shadow-sm">
                    <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
                    ว่าง (Available)
                  </span>
                ` : `
                  <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-rose-500/10 text-rose-400 border border-rose-500/30 shadow-sm animate-pulse">
                    <span class="w-2 h-2 rounded-full bg-rose-400"></span>
                    ไม่ว่าง (In Use)
                  </span>
                `}
              </div>
            </div>

            <!-- Muscle tags -->
            <div class="mt-3 flex flex-wrap gap-1.5">
              ${muscleBadges}
            </div>
          </div>

          <!-- Body: Usage Information -->
          <div class="p-5">
            ${isIdle ? `
              <div class="bg-slate-900/50 rounded-xl p-4 border border-slate-800 flex items-center gap-3">
                <div class="w-10 h-10 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 text-lg">
                  ✨
                </div>
                <div>
                  <p class="text-sm font-semibold text-emerald-300">เครื่องว่าง</p>
                  <p class="text-xs text-slate-400">แตะบัตร NFC ที่เครื่องเล่นเพื่อเริ่มฝึก</p>
                </div>
              </div>
            ` : `
              <div class="bg-rose-950/20 border border-rose-900/40 rounded-xl p-4 space-y-2.5">
                <div class="flex items-center justify-between text-xs">
                  <span class="text-slate-400">ผู้ใช้งานปัจจุบัน:</span>
                  <span class="font-bold text-rose-300 text-sm flex items-center gap-1">
                    👤 ${station.current_user_name || 'Member #' + station.current_user_id}
                  </span>
                </div>
                ${station.current_user_goal ? `
                  <div class="flex items-center justify-between text-xs">
                    <span class="text-slate-400">เป้าหมาย:</span>
                    <span class="text-slate-200">${station.current_user_goal}</span>
                  </div>
                ` : ''}
                ${station.last_active ? `
                  <div class="flex items-center justify-between text-xs pt-1 border-t border-rose-900/30">
                    <span class="text-slate-500">เริ่มเล่นเมื่อ:</span>
                    <span class="text-slate-400 font-mono text-[11px]">${formatActiveTime(station.last_active)}</span>
                  </div>
                ` : ''}
              </div>
            `}
          </div>
        </div>

        <!-- Card Footer / Actions -->
        <div class="px-5 pb-5 pt-0">
          ${!isIdle ? `
            <button onclick="resetStation('${station.station_id}')" 
                    class="w-full bg-slate-700/80 hover:bg-rose-900/50 hover:text-rose-200 hover:border-rose-700/60 border border-slate-600/60 text-slate-300 font-medium py-2 rounded-xl text-xs transition flex items-center justify-center gap-1.5">
              <span>🔓</span> ปรับสถานะเป็น "ว่าง" (Mark as Idle)
            </button>
          ` : `
            <div class="text-center py-1 text-slate-500 text-xs">
              สถานะพร้อมใช้งาน
            </div>
          `}
        </div>

      </div>
    `;
  }).join('');
}

/**
 * ส่งคำขอไปยัง API เพื่อรีเซ็ตสถานะ Station เป็น 'idle'
 */
async function resetStation(stationId) {
  if (!confirm(`ต้องการปรับสถานะเครื่อง "${stationId}" ให้กลับมา "ว่าง" หรือไม่?`)) {
    return;
  }
  try {
    const res = await fetch(`/api/stations/${stationId}/reset`, { method: 'POST' });
    if (res.ok) {
      await fetchStations();
    } else {
      alert('ไม่สามารถรีเซ็ตสถานะได้');
    }
  } catch (err) {
    alert('เกิดข้อผิดพลาดในการเชื่อมต่อ');
  }
}

/**
 * แปลงเวลา last_active ให้อ่านง่าย พร้อมคำนวณระยะเวลาที่กำลังใช้งาน
 */
function formatActiveTime(dateTimeStr) {
  if (!dateTimeStr) return '';
  try {
    const dateObj = new Date(dateTimeStr.replace(' ', 'T'));
    if (!isNaN(dateObj.getTime())) {
      const timeStr = dateObj.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const diffMs = Date.now() - dateObj.getTime();
      const diffMins = Math.max(0, Math.floor(diffMs / 60000));
      if (diffMins > 0) {
        return `${timeStr} (${diffMins} นาทีที่แล้ว)`;
      }
      return `${timeStr} (เพิ่งเริ่ม)`;
    }
  } catch (e) {
    console.error(e);
  }
  const parts = dateTimeStr.split(' ');
  return parts[1] ? `${parts[1]} น.` : dateTimeStr;
}

