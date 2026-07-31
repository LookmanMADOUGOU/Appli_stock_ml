document.addEventListener('DOMContentLoaded', function(){
  const toggle = document.getElementById('sidebar-toggle')
  const sidebar = document.getElementById('sidebar')
  const mobileToggle = document.getElementById('mobile-toggle')

  if(toggle && sidebar){
    toggle.addEventListener('click', ()=>{
      if(sidebar.classList.contains('w-72')){
        sidebar.style.width = '72px'
        sidebar.querySelectorAll('span, .text-xs, .text-sm').forEach(el=>el.style.display='none')
        toggle.innerHTML = '<i class="fas fa-angle-right"></i>'
      } else {
        sidebar.style.width = ''
        sidebar.querySelectorAll('span, .text-xs, .text-sm').forEach(el=>el.style.display='')
        toggle.innerHTML = '<i class="fas fa-angle-left"></i>'
      }
    })
  }

  if(mobileToggle && sidebar){
    mobileToggle.addEventListener('click', ()=>{
      sidebar.classList.toggle('open')
    })
  }
})
