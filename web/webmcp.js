/** Optional imperative tools share the UI actions; unsupported browsers work normally. */
export function registerMapTools({context,snapshot,loadCase,addSegments,caseIds}){
  if(!context?.registerTool)return()=>{};
  const lifecycle=new AbortController();
  const tools=[
    {name:'get_map_state',title:'读取地图状态',description:'Read marker-selection status and verification without changing the drawing.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},execute:input=>{if(!input||Object.keys(input).length)throw new Error('No arguments expected.');return snapshot();}},
    {name:'load_map_case',title:'载入地图案例',description:'Replace the drawing with a built-in case and complete analysis, like the case button. Undo is available.',inputSchema:{type:'object',properties:{caseId:{type:'string',enum:caseIds}},required:['caseId'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:false},execute:input=>{if(!input||Object.keys(input).length!==1||!caseIds.includes(input.caseId))throw new Error('Unknown case.');return loadCase(input.caseId);}},
    {name:'add_map_segments',title:'添加地图线段',description:'Add a batch of segments, identify regions and complete current automatic marker selection. Return after the visible map updates.',inputSchema:{type:'object',properties:{strokes:{type:'array',minItems:1,maxItems:80,items:{type:'object',properties:{a:{type:'array',items:{type:'number'},minItems:2,maxItems:2},b:{type:'array',items:{type:'number'},minItems:2,maxItems:2}},required:['a','b'],additionalProperties:false}}},required:['strokes'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:true},execute:input=>{if(!input||Object.keys(input).length!==1||!Array.isArray(input.strokes))throw new Error('Expected strokes.');return addSegments(input.strokes);}}
  ];
  for(const tool of tools){try{Promise.resolve(context.registerTool(tool,{signal:lifecycle.signal})).catch(()=>{});}catch{/* Optional registration failure must not break drawing. */}}
  const dispose=()=>lifecycle.abort();if(typeof window!=='undefined')window.addEventListener('pagehide',dispose,{once:true});return dispose;
}
