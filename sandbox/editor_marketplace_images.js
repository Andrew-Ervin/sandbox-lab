// Catalog icons point at the sandbox's loopback package broker. Browser images
// must use the authenticated editor origin instead of the user's loopback port.
(() => {
  const prefix = 'http://127.0.0.1:3128/vscode/assets/';
  const update = image => {
    const source = image.getAttribute('src') || '';
    if (source.startsWith(prefix)) image.setAttribute('src', '/__lab/marketplace-icons/' + source.slice(prefix.length));
  };
  const visit = node => {
    if (!(node instanceof Element)) return;
    if (node.matches('img')) update(node);
    node.querySelectorAll('img').forEach(update);
  };
  new MutationObserver(records => records.forEach(record => {
    if (record.type === 'attributes') visit(record.target);
    else record.addedNodes.forEach(visit);
  })).observe(document.documentElement, {subtree:true,childList:true,attributes:true,attributeFilter:['src']});
  visit(document.documentElement);
})();
