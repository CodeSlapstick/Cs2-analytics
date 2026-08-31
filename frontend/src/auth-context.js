import { createContext, useContext } from 'react';

/** แยกไฟล์ context ออกมาต่างหาก เพื่อไม่ให้ App.jsx กับหน้าเพจ import วนกัน */
export const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);
