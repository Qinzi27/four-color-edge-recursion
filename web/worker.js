// Geometry and one-pass marker selection run off the UI thread; no backtracking.
import { analyzeDrawing } from './engine.js';
self.onmessage=event=>{
  const {requestId,document,options}=event.data;
  try { self.postMessage({requestId,result:analyzeDrawing(document,options)}); }
  catch(error) { self.postMessage({requestId,error:{message:error.message,code:error.code||'internal'}}); }
};
