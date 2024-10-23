import { orzMobx , reaxel } from 'reaxes-react';
import "./SearchPopover.css";

type WebsiteSummary = Partial<Record<"title" | "favico" | "description" | "hostname" , string | null | undefined>>;

/**
 * reaxel module是一种"让应用逻辑以分布式、响应式、不依赖视图的方式低耦合且高内聚组合在一起的编程范式",应用逻辑从此完全不依赖于视图
 * 
 * 每个模块的逻辑封闭在自己的reaxel中,并对外暴露必要的接口,这样的架构使得reaxes对前后端同构的应用天然友好,因为前后端都可以用同一套reaxel module
 * 
 * 各个reaxel的相互依赖会在页面部署完成之后就会立刻建立完成,这意味着应用的核心逻辑优先于视图初始化完毕
 * 
 * 无论你使用react,vue2,vue3,还是solidjs,只需要使用reaxel编写一次核心逻辑,就可以在它们之间无缝切换,甚至在同一个页面的不同部分分别使用react和vue也完全可行!
 */
export const reaxel_SearchPopover = reaxel( () => {
  /**
   * 创建一个基于mobx observable的store,mutate可以使得改变深层状态变得十分简单,不需要setState({...store})嵌套多层
   * 
   * urlMaps将每个独特的url当做key来做缓存, 使得重复载入多次时不必重新执行完整链路的requestWebsiteSummary, 在需要的时候可以随时释放掉引用
   */
  const { store , setState , mutate } = orzMobx( {
    urlMaps : {} as {
      [p: string]: {
        finished? : boolean,
        fetching? : boolean,
      } & WebsiteSummary
    } ,
  } );
  
  //根据url去请求该网址的所有摘要信息，如title，description等
  const requestWebsiteSummary = async (url:string) => {
    if(store.urlMaps[url]?.finished || store.urlMaps[url]?.fetching){
      return;
    }
    mutate(s => s.urlMaps[url] = {fetching:true});
    
    const text = await fetch(url).then(res => res.text());
    const doc = (new DOMParser()).parseFromString(text, 'text/html');
    const title = doc.querySelector('title')?.innerText;
    const {hostname,protocol,} = new URL(url);
    let favico = (doc.querySelector("link[rel~='icon']") as HTMLLinkElement)?.href;
    const favicoURL = new URL(favico);
    if(favico.startsWith('http://')){
      favico = `${protocol}//${hostname}${favicoURL.pathname}`;
    }
    
    //desc要做大量兼容性处理,确保抓取到目标网页的摘要信息,这里暂时假设网址都有og:description
    const description = (doc.head.querySelector( 'meta[property="og:description"]') as HTMLMetaElement)?.content;
    //暂时假设url都是合法的
    const result:WebsiteSummary = { title , favico , description , hostname };
    
    mutate( s => Object.assign( s.urlMaps[url] , result ,{finished:true,fetching:false}) );
    
    return result;
  }
  
  //这是每个reaxel module最终要暴露出去的接口
  const ret = {
    SearchPopover_Store:store,
    SearchPopover_SetState:setState,
    SearchPopover_Mutate : mutate,
    requestWebsiteSummary,
  };
  
  return () => {
    return ret;
  };
} );





