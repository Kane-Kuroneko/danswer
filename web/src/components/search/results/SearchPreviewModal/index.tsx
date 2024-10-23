"use client";

import {reaxper,reaxel,orzMobx,Reaxes} from 'reaxes-react';

import { Message } from "../../../../app/chat/interfaces";
import { ForwardedRef , forwardRef } from "react";
import { usePopup } from "@/components/admin/connectors/Popup";
import { DanswerDocument } from "@/lib/search/interfaces";
import { Divider , Text } from "@tremor/react";
import { ChatDocumentDisplay } from "../../../../app/chat/documentSidebar/ChatDocumentDisplay";
import { removeDuplicateDocs } from "@/lib/documentUtils";
import { XIcon } from '../../../../components/icons/icons';

import { reaxel_SearchPopover } from '../SearchPopover/SearchPopover.reaxel';
import { reaxel_SearchPreviewModal } from './SearchPreviewModal.reaxel';

import './SearchPreviewModal.css';

interface DocumentSidebarProps {
  closeSidebar: () => void;
  selectedMessage: Message | null;
  selectedDocuments: DanswerDocument[] | null;
  toggleDocumentSelection: (document: DanswerDocument) => void;
  clearSelectedDocuments: () => void;
  selectedDocumentTokens: number;
  maxTokens: number;
  isLoading: boolean;
  initialWidth: number;
  isOpen: boolean;
}

export const SearchPreviewModal = reaxper(forwardRef<HTMLDivElement, DocumentSidebarProps>(
  (
    {
      closeSidebar,
      selectedMessage,
      selectedDocuments,
      toggleDocumentSelection,
      clearSelectedDocuments,
      selectedDocumentTokens,
      maxTokens,
      isLoading,
      initialWidth,
      isOpen,
    },
    ref: ForwardedRef<HTMLDivElement>
  ) => {
    const {SearchPopover_Store,} = reaxel_SearchPopover();
    const {SearchPreviewModal_Store,loadUrl,toggleOpen,} = reaxel_SearchPreviewModal();
    const { url } = SearchPreviewModal_Store;
    isOpen = SearchPreviewModal_Store.isOpen;
    const { popup, setPopup } = usePopup();
    
    const selectedDocumentIds =
      selectedDocuments?.map((document) => document.document_id) || [];
    
    const currentDocuments = selectedMessage?.documents || null;
    const dedupedDocuments = removeDuplicateDocs(currentDocuments || []);
    
    // NOTE: do not allow selection if less than 75 tokens are left
    // this is to prevent the case where they are able to select the doc
    // but it basically is unused since it's truncated right at the very
    // start of the document (since title + metadata + misc overhead) takes up
    // space
    const tokenLimitReached = selectedDocumentTokens > maxTokens - 75;
    
    if(!SearchPopover_Store.urlMaps[url]){
      return null;
    }
    
    return (
      <div
        className = { `ml-auto rounded-l-lg relative border-l bg-text-100 sidebar z-50 right-0 h-screen transition-all duration-150 ${
          isOpen ? "opacity-100 translate-x-0" : "opacity-0 translate-x-[10%]"
        }` }
        data-search-preview-modal = { isOpen ? 'isOpen' : '' }
        ref = { ref }
      >
        <div className = "pb-6  overflow-y-hidden flex flex-col h-full">
          { popup }
          <div className = "pl-3 mx-2 pr-6 mt-3 flex text-text-800 text-2xl text-emphasis flex font-semibold">
            <img src={SearchPopover_Store.urlMaps[url]?.favico ?? ''}/>
            <span className="pl-3">{url ?? SearchPopover_Store.urlMaps[url].title}</span>
          </div>
          
          <Divider className = "mb-0 mt-4 pb-2" />
          
          {SearchPreviewModal_Store.iframe}
        </div>
        
        <div
          className = "absolute left-0 bottom-0 w-full bg-gradient-to-b from-neutral-100/0 via-neutral-100/40 backdrop-blur-xs to-neutral-100 h-[100px]"
          style = { { borderRadius : '1em' } }
        />
        <button
          className="absolute right-[24px] top-[24px] scale-150 cursor-pointer"
          onClick = { () => toggleOpen() }
        >
          <XIcon className = "w-5 h-5" />
        </button>
      </div>
    );
  }
));

