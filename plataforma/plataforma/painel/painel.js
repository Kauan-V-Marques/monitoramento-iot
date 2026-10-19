// Painel ao vivo: carrega o estado pela API REST e recebe as novidades pelo WebSocket.

const estado = { maquinas: new Map(), selecionada: null, grafico: null };
const el = {
  grade: document.querySelector('#maquinas'),
  alertas: document.querySelector('#alertas'),
  conexao: document.querySelector('#conexao'),
  titulo: document.querySelector('#titulo-grafico'),
  periodo: document.querySelector('#periodo'),
};

const ROTULOS = { temperatura: 'temperatura', vibracao: 'vibração' };
const fmt = (valor, casas) => (valor === null || valor === undefined ? '—' : Number(valor).toFixed(casas));
const hora = (iso) => new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const escapar = (texto) =>
  String(texto).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

function cartaoMaquina(m) {
  const tempRuim = m.temperatura_c !== null && m.temperatura_c > m.limite_temperatura_c;
  const vibRuim = m.vibracao_rms_g > m.limite_vibracao_g;
  return `
    <article class="cartao maquina ${m.alertas_abertos > 0 ? 'alerta' : ''} ${m.id === estado.selecionada ? 'selecionada' : ''}"
             data-id="${escapar(m.id)}" tabindex="0" aria-label="Máquina ${escapar(m.id)}">
      <div class="maquina-topo">
        <span class="nome">${escapar(m.nome)}</span>
        <span class="status ${m.online ? 'online' : ''}">${m.online ? 'online' : 'offline'}</span>
      </div>
      <div class="medidas">
        <div class="medida ${tempRuim ? 'ruim' : ''}"><span>Temperatura</span><strong>${fmt(m.temperatura_c, 1)} °C</strong></div>
        <div class="medida ${vibRuim ? 'ruim' : ''}"><span>Vibração RMS</span><strong>${fmt(m.vibracao_rms_g, 2)} g</strong></div>
        <div class="medida"><span>Corrente</span><strong>${fmt(m.corrente_a, 1)} A</strong></div>
        <div class="medida"><span>Rotação</span><strong>${fmt(m.rpm, 0)} rpm</strong></div>
      </div>
    </article>`;
}

function desenharMaquinas() {
  el.grade.innerHTML = [...estado.maquinas.values()].map(cartaoMaquina).join('') ||
    '<p class="vazio">Nenhuma máquina enviou dados ainda. Rode o simulador ou ligue um ESP32.</p>';
}

async function carregarAlertas() {
  const alertas = await (await fetch('/api/alertas')).json();
  el.alertas.innerHTML = alertas.length
    ? alertas.map((a) => `
        <li>
          <span class="${a.fim ? '' : 'aberto'}">${a.fim ? 'Encerrado' : 'ABERTO'}: ${ROTULOS[a.tipo] ?? escapar(a.tipo)} em ${escapar(a.maquina_id)}</span><br>
          <span class="quando">${hora(a.inicio)} · ${fmt(a.valor, 2)} (limite ${fmt(a.limite, 2)})${a.fim ? ` · até ${hora(a.fim)}` : ''}</span>
        </li>`).join('')
    : '<li class="vazio">Nenhum alerta até agora.</li>';
}

function criarGrafico() {
  const ctx = document.querySelector('#grafico');
  const eixo = (id, cor, posicao) => ({ id, position: posicao, ticks: { color: cor }, grid: { color: '#262c38' } });
  estado.grafico = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'Temperatura (°C)', data: [], borderColor: '#f5b83d', yAxisID: 'temp', tension: 0.3, pointRadius: 0 },
        { label: 'Vibração RMS (g)', data: [], borderColor: '#5aa7ff', yAxisID: 'vib', tension: 0.3, pointRadius: 0 },
      ],
    },
    options: {
      animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: '#e7eaf0' } } },
      scales: {
        x: { ticks: { color: '#8d96a8', maxTicksLimit: 8 }, grid: { color: '#262c38' } },
        temp: eixo('temp', '#f5b83d', 'left'),
        vib: eixo('vib', '#5aa7ff', 'right'),
      },
    },
  });
}

async function selecionar(id) {
  estado.selecionada = id;
  el.titulo.textContent = `Histórico · ${id}`;
  desenharMaquinas();
  const pontos = await (await fetch(`/api/maquinas/${encodeURIComponent(id)}/historico?minutos=${el.periodo.value}`)).json();
  const g = estado.grafico;
  g.data.labels = pontos.map((p) => hora(p.tempo));
  g.data.datasets[0].data = pontos.map((p) => p.temperatura_c);
  g.data.datasets[1].data = pontos.map((p) => p.vibracao_rms_g);
  g.update();
}

function aoReceber(evento) {
  if (evento.tipo === 'leitura') {
    const m = estado.maquinas.get(evento.maquina);
    if (!m) return void carregarMaquinas();
    Object.assign(m, evento, { online: true });
    if (evento.maquina === estado.selecionada) {
      const g = estado.grafico;
      g.data.labels.push(hora(evento.ts));
      g.data.datasets[0].data.push(evento.temperatura_c);
      g.data.datasets[1].data.push(evento.vibracao_rms_g);
      if (g.data.labels.length > 300) [g.data.labels, ...g.data.datasets.map((d) => d.data)].forEach((a) => a.shift());
      g.update();
    }
    desenharMaquinas();
  } else if (evento.tipo === 'alerta') {
    const m = estado.maquinas.get(evento.maquina);
    if (m) m.alertas_abertos = Math.max(0, (m.alertas_abertos ?? 0) + (evento.aberto ? 1 : -1));
    desenharMaquinas();
    carregarAlertas();
  } else if (evento.tipo === 'status') {
    const m = estado.maquinas.get(evento.maquina);
    if (m) m.online = evento.online;
    desenharMaquinas();
  }
}

async function carregarMaquinas() {
  const lista = await (await fetch('/api/maquinas')).json();
  estado.maquinas = new Map(lista.map((m) => [m.id, m]));
  desenharMaquinas();
  if (!estado.selecionada && lista.length) selecionar(lista[0].id);
}

function conectar() {
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => {
    el.conexao.textContent = 'ao vivo';
    el.conexao.classList.add('on');
  };
  ws.onmessage = (mensagem) => aoReceber(JSON.parse(mensagem.data));
  ws.onclose = () => {
    el.conexao.textContent = 'reconectando…';
    el.conexao.classList.remove('on');
    setTimeout(conectar, 2000);
  };
}

el.grade.addEventListener('click', (e) => {
  const cartao = e.target.closest('.maquina');
  if (cartao) selecionar(cartao.dataset.id);
});
el.grade.addEventListener('keydown', (e) => {
  const cartao = e.target.closest('.maquina');
  if (cartao && (e.key === 'Enter' || e.key === ' ')) selecionar(cartao.dataset.id);
});
el.periodo.addEventListener('change', () => estado.selecionada && selecionar(estado.selecionada));

criarGrafico();
carregarMaquinas();
carregarAlertas();
conectar();
