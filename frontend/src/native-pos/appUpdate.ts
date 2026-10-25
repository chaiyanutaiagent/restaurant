import { Capacitor, registerPlugin } from '@capacitor/core';
import { create } from 'zustand';
import { nativeProduct } from './config';
import { verifyPosRelease, type PosRelease } from './updatePolicy';
import { readNativeTransaction } from './transactionJournal';
import { hasNativePaymentPending } from './paidOrderRecovery';
import { nativeScope, readNativeCart } from './storage';
export type InstalledPosApp={packageId:string;versionCode:number;versionName:string};
export interface PosUpdater {
  getStatus():Promise<InstalledPosApp>;
  getRelease():Promise<{manifest:unknown}>;
  installUpdate(options:{apkUrl:string;apkSha256:string;versionCode:number}):Promise<void>;
}
const updater=registerPlugin<PosUpdater>('NativePosUpdater');
export const usePosUpdate=create<{release:PosRelease|null;installed:InstalledPosApp|null;checking:boolean;installing:boolean;message:string;dismissed:number|null}>(()=>({release:null,installed:null,checking:false,installing:false,message:'',dismissed:null}));
export async function checkPosUpdate(manual=false) {
  if(usePosUpdate.getState().checking || usePosUpdate.getState().installing) return;
  if(!Capacitor.isNativePlatform()) { if(manual) usePosUpdate.setState({message:'ตรวจอัปเดตได้ในแอป Android เท่านั้น'}); return; }
  usePosUpdate.setState({checking:true});
  try {
    const [installed,{manifest}]=await Promise.all([updater.getStatus(),updater.getRelease()]);
    const release=await verifyPosRelease(manifest,nativeProduct ?? '');
    if(installed.packageId!==release.package_id)throw Error('ช่องอัปเดตไม่ตรงกับแอปที่ติดตั้ง');
    const available=release.version_code>installed.versionCode;
    usePosUpdate.setState({installed,release:available?release:null,message:manual?(available?'มีเวอร์ชันใหม่พร้อมดาวน์โหลด':'เป็นเวอร์ชันล่าสุดแล้ว'):'',...(manual?{dismissed:null}:{})});
  } catch(error) {
    // Never gate offline startup or selling on a failed update check.
    if(manual) usePosUpdate.setState({message:error instanceof Error?error.message:'ตรวจอัปเดตไม่ได้ กรุณาลองใหม่'});
  } finally { usePosUpdate.setState({checking:false}); }
}
export async function assertPosUpdateSafe() {
  if(await readNativeTransaction() || await hasNativePaymentPending()) throw Error('มีรายการรับเงินรอตรวจสอบ กรุณาจัดการรายการเดิมก่อนอัปเดต');
  for(const suffix of ['counter','takeaway']) {
    const cart=await readNativeCart(`${nativeScope()}:${suffix}`);
    if(cart?.cartItems?.length || cart?.items?.length) throw Error('มีสินค้าในตะกร้า กรุณาพักบิลหรือทำรายการให้เสร็จก่อนอัปเดต');
  }
}
export async function installPosUpdate() {
  const state=usePosUpdate.getState(); if(state.installing || !state.release) return;
  usePosUpdate.setState({installing:true,message:''});
  try {
    if(!navigator.onLine) throw Error('ต้องออนไลน์เพื่อดาวน์โหลดอัปเดต');
    await assertPosUpdateSafe();
    const release=await verifyPosRelease({...state.release},nativeProduct ?? '');
    const installed=await updater.getStatus();
    if(installed.packageId!==release.package_id || installed.versionCode>=release.version_code) throw Error('ไม่มีรุ่นใหม่ที่ติดตั้งได้ กรุณาตรวจอีกครั้ง');
    await updater.installUpdate({apkUrl:release.apk_url,apkSha256:release.apk_sha256,versionCode:release.version_code});
    usePosUpdate.setState({message:'กรุณายืนยันติดตั้งในหน้าของ Android ข้อมูลและการจับคู่เครื่องจะยังอยู่'});
  } catch(error) { usePosUpdate.setState({message:error instanceof Error?error.message:'อัปเดตไม่ได้ กรุณาลองใหม่'}); }
  finally { usePosUpdate.setState({installing:false}); }
}
