

function wrap(obj, meth) {
   var orig = obj[meth];
   obj[meth] = function wrapper() {
       var lang = null;
       try {
           if (window.GamingContext && window.GamingContext.languageId != null) {
               lang = window.GamingContext.languageId;
           }
       } catch (e) {}
       window.dispatchEvent(new CustomEvent('sendToAPI', {
           detail: { data: arguments[0], lang: lang }
       }));
       return orig.apply(this, arguments);
   }
}

function hookSocket(){
    if(window.readit){
        wrap(window.readit.WebsocketTransportMethod.prototype, 'socketDataCallback');
    }
    else {
        setTimeout(hookSocket, 1000);
    }
}

setTimeout(hookSocket, 1000);

