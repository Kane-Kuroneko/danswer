import React , { useState  } from "react";
import { reaxper  } from 'reaxes-react';
import { Popover } from 'antd';
import { reaxel_SearchPopover } from './SearchPopover.reaxel';
import { reaxel_SearchPreviewModal } from '../SearchPreviewModal/SearchPreviewModal.reaxel';

import "./SearchPopover.css";

export type SearchPopoverProps = React.PropsWithChildren<{
  url : string,
}>

//reaxper类似于mobx-react::observer,使组件订阅mobx store. reaxper还可以让class组件的render函数使用hooks
export const SearchPopover = reaxper( ( {
  url,
  children,
}: SearchPopoverProps ) => {
  
  //直接勾入reaxel就可以拿到所有需要的方法和状态.
  const {SearchPreviewModal_Store} = reaxel_SearchPreviewModal();
  const {SearchPopover_Store,requestWebsiteSummary,} = reaxel_SearchPopover();
  
  const {fetching,finished,title,hostname,description,favico} = SearchPopover_Store.urlMaps[url] ?? {};
  const [ popoverIsOpen , setPopoverIsOpen ] = useState( false );
  const popoverOpen = SearchPreviewModal_Store.isOpen ? false : popoverIsOpen;
  
  if(url && !fetching && !finished){
    requestWebsiteSummary( url );
  }
  
  return <Popover
    open={popoverOpen}
    onOpenChange={setPopoverIsOpen}
    title = { finished && !fetching && <PopoverTitle
      favico = { favico }
      hostname = { hostname }
    /> }
    content = { finished && !fetching && <PopoverContent
      title = { title }
      url = { url }
      description = { description }
      setPopoverIsOpen = {setPopoverIsOpen}
    /> }
  > { children } </Popover>;
} );



const PopoverTitle = reaxper( ( props: React.PropsWithChildren<{
  favico?: string|null,
  hostname?: string | null,
}> ) => {
  return <div className="search-popover-title">
    <img src = { props.favico ?? '' } />
    <span>{ props.hostname }</span>
  </div>;
} );



const PopoverContent = reaxper( ( props: React.PropsWithChildren<{
  title?: string | null,
  url?: string | null,
  description?: string | null,
  setPopoverIsOpen: ( status: boolean ) => void,
}> ) => {
  const { SearchPreviewModal_Store , loadUrl , toggleOpen } = reaxel_SearchPreviewModal();
  return <div className = "search-popover-content">
    <a
      href = { props.url ?? '' }
      onClick = { ( e ) => {
        e.preventDefault();
        loadUrl( props.url ?? '' );
        toggleOpen( true );
        props.setPopoverIsOpen( false );
      } }
    >{ props.title }</a>
    <div>{ props.description }</div>
  </div>;
} );
