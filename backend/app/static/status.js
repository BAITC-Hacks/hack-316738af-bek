fetch('/api/health').then(response => {
  if (!response.ok) throw new Error('health');
  return response.json();
}).then(data => {
  const health = document.querySelector('#health');
  health.classList.add('ready');
  health.querySelector('span').textContent = 'Сервер жұмыс істеп тұр';
  document.querySelector('#openai').textContent = data.openai_configured ? 'Орнатылған' : 'Орнатылмаған';
  document.querySelector('#nvidia').textContent = data.nvidia_configured ? 'Қосылған' : 'Өшірулі';
}).catch(() => {
  document.querySelector('#health span').textContent = 'Серверге қосылу мүмкін болмады';
  document.querySelector('#openai').textContent = 'Белгісіз';
  document.querySelector('#nvidia').textContent = 'Белгісіз';
});
