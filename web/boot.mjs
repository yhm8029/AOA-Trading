// v0.4.1: verify process, UI source, and version BEFORE enabling chart actions.
import {UI_VERSION} from './study-ui.mjs?v=041';
const style=document.createElement('link');style.rel='stylesheet';style.href='/launch.css?v=041';document.head.append(style);
const info=document.getElementById('runtimeInfo');
const warning=document.getElementById('versionWarning');
const workspace=document.querySelector('.workspace');
workspace.inert=true;
window.AOALaunchState={verified:false};
try {
  const expected=new URLSearchParams(location.search);
  const r=await fetch('/api/runtime',{cache:'no-store'});
  if(!r.ok)throw Error('실행 확인 API가 없는 이전 서버입니다. 새 폴더의 start_windows.bat가 여는 새 주소를 사용하세요.');
  const data=await r.json();
  if(data.application!=='AOA-Whale-Viewer'||data.version!==UI_VERSION||document.getElementById('version').textContent!=='v'+UI_VERSION)
    throw Error(`화면 ${UI_VERSION} / 서버 ${data.version||'미확인'} 버전 불일치. 파일을 섞지 말고 새 ZIP을 빈 폴더에 풀어 실행하세요.`);
  if(expected.has('launch')&&expected.get('launch')!==data.instance)
    throw Error('다른 실행 세션의 오래된 주소입니다. 이번 실행 콘솔의 OPEN THIS URL 주소를 열어 주세요.');
  const htmlResponse=await fetch('/index.html',{cache:'no-store'});
  if(!htmlResponse.ok)throw Error('현재 화면 원본 확인 실패');
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await htmlResponse.arrayBuffer()))).map(n=>n.toString(16).padStart(2,'0')).join('');
  if(digest!==data.ui_sha256)throw Error('실행 도중 화면 파일이 변경됐습니다. 새 앱을 다시 실행하세요.');
  const required=['entryFocus','lastFocus','autoFill','studyPanel','pauseOnEvent'];
  if(required.some(id=>!document.getElementById(id)))throw Error('캐시된 초기 화면입니다. Ctrl+F5 후 새 실행 주소를 여세요.');
  document.getElementById('runtimeText').textContent=`버전: ${data.version}\n앱 폴더: ${data.app_dir}\n데이터 폴더: ${data.data_dir}\n포트: ${data.port}\n프로세스: ${data.pid}\n실행 ID: ${data.instance}`;
  info.querySelector('summary').textContent=`실행 확인 v${data.version}`;
  window.AOALaunchState={verified:true,...data};
  await import('./app.mjs?v=041');
  workspace.inert=false;
} catch(error) {
  warning.hidden=false;warning.textContent='실행 중단: '+error.message;
  document.getElementById('empty').hidden=true;
  info.querySelector('summary').textContent='버전/실행 확인 실패';
  window.AOALaunchState={verified:false,error:error.message};
  console.error(error);
}
