import { orzMobx , reaxel , Reaxes } from 'reaxes-react';

export const reaxel_SearchPreviewModal = reaxel( () => {
  /**
   * 创建一个基于mobx observable的store,mutate可以使得改变深层状态变得十分简单,不需要setState({...store})嵌套多层
   * 
   * 这个store用于控制preview窗口的内容和加载状态
   */
  const {
    store ,
    setState ,
    mutate ,
  } = orzMobx( {
    isOpen : false ,
    url : null as unknown as string,
    loaded:false,
    loading: false,
    iframe : null as unknown as React.ReactElement | null,
  } );
  
  const toggleOpen = ( open = !store.isOpen ) => mutate( s => s.isOpen = open );
  
  const createReactIframe = (url:string,onload?:React.EventHandler<any> ) => {
    return <iframe onLoad={onload} src = { url } width="100%" height="100%"/>;
  }
  
  const loadUrl = (url:string) => {
    setState( { url } );
  }
  
  /**
   * Reaxes.obsReaction是reaxes的核心功能,它的第二个参数告诉这个reaction当哪些observable属性变化时来重新运行callback
   * 
   * 每个reaxel module之间的依赖关系通过Reaxes.obsReaction建立.
   * 
   * 也用于当相关prop变化时执行核心逻辑和副作用 , 
   * 这样的好处是完全避免了react hooks一遍遍的刷新组件,
   * 极大地消耗了CPU资源也造成UI界面卡顿
   * 直到稳定态之前的绝大多数hooks引起的组件刷新都是完全无必要的,
   * 而且hooks也带来了严重的心智负担
   */
  Reaxes.obsReaction(() => {
    const {url,loading} = store;
    if(!store.url) {
      setState( {
        loaded : false ,
        loading : false ,
        iframe : null ,
      } );
      return;
    };
    if(loading){
      return;
    }
    setState({
      loaded : false,
      loading : true,
      iframe : createReactIframe(url,() =>{
        setState( {
          loaded : true ,
          loading : false ,
        } );
      } ) ,
    } );
  } , () => [ store.url ] );
  
  const ret = {
    //对外暴露store时加上模块的名字,不然每次使用时都要重新起名来避免命名空间冲突
    SearchPreviewModal_Store : store ,
    SearchPreviewModal_SetState : setState ,
    SearchPreviewModal_Mutate : mutate ,
    loadUrl ,
    toggleOpen ,
    /**
     * 这里之所以不直接写open:store.isOpen , 是想在其他地方使用ret.open时不丢失observable props的传染性,
     * 使得UI组件/obsReaction都可以监听它的变化.
     */
    get open() {
      return store.isOpen;
    } ,
  };
  
  return () => {
    return ret;
  };
} );

