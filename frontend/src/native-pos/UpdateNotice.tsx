import { useEffect } from 'react';
import { App } from '@capacitor/app';
import { Capacitor } from '@capacitor/core';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { checkPosUpdate, installPosUpdate, usePosUpdate, assertPosUpdateSafe } from './appUpdate';
import { useAuthStore } from './session';

export default function UpdateNotice() {
  const state=usePosUpdate(); const location=useLocation();
  const navigate=useNavigate();
  const authenticated=useAuthStore(s=>Boolean(s.accessToken));
  useEffect(()=>{
    void checkPosUpdate();
    const check=()=>{void checkPosUpdate();};
    window.addEventListener('online',check);
    const timer=window.setInterval(check,6*60*60*1000);
    const listener=Capacitor.isNativePlatform()?App.addListener('appStateChange',({isActive})=>{if(isActive)check();}):null;
    return ()=>{window.removeEventListener('online',check);window.clearInterval(timer);void listener?.then(handle=>handle.remove());};
  },[]);
  if(state.installing) return <div role="dialog" aria-modal="true" aria-label="กำลังอัปเดตแอป" className="fixed inset-0 z-[200] flex items-center justify-center bg-slate-950/80 p-5"><div className="rounded-2xl bg-white p-6">กำลังดาวน์โหลดและตรวจสอบ APK… กรุณารอสักครู่ ไม่ต้องลบแอปเดิม</div></div>;
  const device=authenticated && location.pathname==='/native/device';
  if(!state.release || (!device && state.dismissed===state.release.version_code))return device && state.message?<p role="status" className="p-3 text-sm">{state.message}</p>:null;
  return <aside role="status" className="flex flex-wrap items-center gap-3 border-b border-blue-200 bg-blue-50 p-3 text-sm text-blue-950">
    <span>มีแอปเวอร์ชันใหม่ {state.installed?.versionName} → {state.release.version_name}</span>
    {device?<button className="min-h-11 rounded bg-blue-700 px-4 text-white" onClick={()=>{void installPosUpdate();}}>ดาวน์โหลดและติดตั้ง</button>:<Link className="min-h-11 rounded border border-blue-300 p-3" to="/native/device" onClick={async event=>{
      event.preventDefault();
      try { await assertPosUpdateSafe(); if(window.confirm('ทำรายการหรือพักบิลเรียบร้อยแล้วใช่ไหม? เปิดหน้าตั้งค่าเพื่ออัปเดตแอป')) navigate('/native/device'); }
      catch(error){usePosUpdate.setState({message:error instanceof Error?error.message:'กรุณาตรวจรายการค้างก่อน'});}
    }}>อัปเดตเมื่อพร้อม</Link>}
    <button className="min-h-11 underline" onClick={()=>usePosUpdate.setState({dismissed:state.release!.version_code, ...(device?{release:null}:{})})}>ไว้ทีหลัง</button>
    {device && <p className="w-full">ต้องไม่มีตะกร้าหรือรายการรับเงินค้าง Android จะให้ยืนยันก่อนติดตั้ง</p>}
    {state.message && <p className="w-full">{state.message}</p>}
  </aside>;
}
