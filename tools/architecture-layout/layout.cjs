// JSON in, JSON out. No network, model calls, or generated executable code.
const ELK = require('elkjs/lib/elk.bundled.js');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  input += chunk;
  if (input.length > 1000000) process.exit(2);
});
process.stdin.on('end', async () => {
  try {
    const graph = JSON.parse(input);
    const engine = new ELK();
    let result;
    if (graph.compactHierarchy) {
      // Layout each real boundary independently. Global layered layout otherwise
      // stretches an entire VPC/region to the rank of a distant external node.
      // Quotient edges are layout hints only; Python routes every original edge.
      const allEdges = [];
      const collect = item => {
        allEdges.push(...(item.edges || []));
        (item.children || []).forEach(collect);
      };
      collect(graph);
      const leaves = item => item.children ? item.children.flatMap(leaves) : [item.id];
      async function arrange(item) {
        if (!item.children) return item;
        const children = [];
        for (const child of item.children) children.push(await arrange(child));
        // Global identity must remain outside Region, without consuming an empty
        // full-height side column and lengthening every regional connection.
        if (item.id.startsWith('__aws_account') &&
            children.some(c=>c.id.startsWith('__region')) &&
            children.every(c=>c.id.startsWith('__region') || c.id.startsWith('__shared_controls'))) {
          let y=48,width=0;
          for (const child of [...children.filter(c=>c.id.startsWith('__shared_controls')),
                               ...children.filter(c=>c.id.startsWith('__region'))]) {
            if (child.id.startsWith('__shared_controls')) {
              child.children.forEach((c,i)=>{c.x=24+i*(c.width+32);c.y=44;});
              child.width=48+child.children.reduce((n,c)=>n+c.width+32,0)-32;
              child.height=64+Math.max(...child.children.map(c=>c.height));
            }
            child.x=14;child.y=y;y+=child.height+20;width=Math.max(width,child.width);
          }
          return {...item,children,edges:[],width:width+28,height:y};
        }
        // Independent business paths get separate compact rows. This applies
        // only to direct regional services: never flatten VPC/AZ/subnet ownership.
        if (graph.flowLanes && item.id.startsWith('__region') &&
            children.every(c => !c.children || c.id.startsWith('__shared_controls')) &&
            children.some(c => !c.children && !c.flowId)) {
          // Shared services belong in one connected spine, not a separate row.
          const services=children.filter(c=>!c.children), ids=new Set(services.map(c=>c.id));
          const spine=await engine.layout({id:'spine',children:services,
            edges:allEdges.filter(e=>ids.has(e.sources[0]) && ids.has(e.targets[0]))
              .map(e=>({id:e.id,sources:e.sources,targets:e.targets})),
            layoutOptions:{...graph.layoutOptions,'elk.direction':'RIGHT',
              'elk.padding':'[top=16,left=16,bottom=16,right=16]',
              'elk.layered.spacing.nodeNodeBetweenLayers':'48'}});
          // A terminal dependency of a shared integration hub is a branch, not
          // another stage between that hub and its external client system.
          for (const hub of spine.children.filter(c=>!c.flowId)) {
            const externalPeers=allEdges.filter(e=>e.sources[0]===hub.id && !ids.has(e.targets[0]));
            if (!externalPeers.length) continue;
            let branchY=hub.y+hub.height+48;
            for (const leaf of spine.children.filter(c=>c.id!==hub.id)) {
              const incoming=allEdges.filter(e=>e.targets[0]===leaf.id);
              const outgoing=allEdges.filter(e=>e.sources[0]===leaf.id);
              if (incoming.length===1 && incoming[0].sources[0]===hub.id && !outgoing.length) {
                const x=hub.x,y=branchY;
                const blocked=spine.children.some(c=>c!==leaf && c!==hub &&
                  x<c.x+c.width && x+leaf.width>c.x && y<c.y+c.height && y+leaf.height>c.y);
                if (!blocked) {leaf.x=x;leaf.y=y;branchY+=leaf.height+48;}
              }
            }
          }
          spine.width=Math.max(...spine.children.map(c=>c.x+c.width))+16;
          spine.height=Math.max(...spine.children.map(c=>c.y+c.height))+16;
          let y=48,width=spine.width+28;
          const placed=[];
          for (const control of children.filter(c=>c.children)) {
            let x=24;
            control.children.forEach(c=>{c.x=x;c.y=44;x+=c.width+24;});
            control.width=x;control.height=64+Math.max(...control.children.map(c=>c.height));
            control.x=14;control.y=y;y+=control.height+24;width=Math.max(width,control.width+28);
            placed.push(control);
          }
          placed.push(...spine.children.map(c=>({...services.find(n=>n.id===c.id),x:c.x+14,y:c.y+y})));
          return {...item,children:placed,edges:[],width,height:y+spine.height+14};
        }
        if (graph.flowLanes && item.id.startsWith('__region') &&
            children.every(c => !c.children || c.id.startsWith('__shared_controls')) &&
            children.some(c => c.flowId) &&
            children.filter(c => !c.children).every(c => c.flowId)) {
          const flowIds = [...new Set([...(graph.flows || []).map(f => f.id),
            ...children.filter(c => c.flowId).map(c => c.flowId)])];
          const rows = flowIds.map(id => children.filter(c => !c.children && c.flowId === id)).filter(r => r.length);
          const unassigned = children.filter(c => !c.children && !c.flowId);
          if (unassigned.length) rows.push(unassigned);
          let y = 52, width = 0;
          const placedChildren = [];
          for (const row of rows) {
            const ids = new Set(row.map(c => c.id));
            const flow = (graph.flows || []).find(f => f.id === row[0].flowId);
            const source = flow?.paths?.[0]?.[0];
            const sourceIsHub = source && allEdges.filter(e => e.targets[0] === source).length >
              allEdges.filter(e => e.sources[0] === source).length;
            const lane = await engine.layout({id:'lane', children:row.map(c => ({...c})),
              edges:allEdges.filter(e => ids.has(e.sources[0]) && ids.has(e.targets[0]))
                .map(e => ({id:e.id,sources:e.sources,targets:e.targets})),
              layoutOptions:{...graph.layoutOptions, 'elk.direction':sourceIsHub?'LEFT':'RIGHT',
                'elk.padding':'[top=50,left=24,bottom=18,right=24]',
                'elk.layered.spacing.nodeNodeBetweenLayers':'56'}});
            placedChildren.push({id:'__flowlane_'+item.id+'_'+placedChildren.length,
              x:14,y,width:lane.width,height:lane.height,
              labels:[{text:flow?.label || 'Supporting services'}],
              children:lane.children.map(p => ({...row.find(c => c.id === p.id),x:p.x,y:p.y}))});
            width = Math.max(width,lane.width); y += lane.height+24;
          }
          for (const controls of children.filter(c => c.children)) {
            // A support rail, not a tall column competing with the main workflows.
            let x = 24;
            controls.children.forEach(c => {c.x=x;c.y=48;x+=c.width+32;});
            controls.width=x-8;
            controls.height=72+Math.max(...controls.children.map(c=>c.height));
            placedChildren.push({...controls,x:14,y});
            width=Math.max(width,controls.width+28); y+=controls.height+24;
          }
          for (const row of placedChildren.filter(c=>c.id.startsWith('__flowlane'))) {
            const shift=(width-row.width)/2;
            row.children.forEach(c=>{c.x+=shift;});
            row.width=width;
          }
          // Flow rows are layout scaffolding, not deployment/subsystem boundaries.
          // Preserve positions while removing invented per-feature containers.
          const flattened = placedChildren.flatMap(c => c.id.startsWith('__flowlane_')
            ? c.children.map(n => ({...n,x:n.x+c.x,y:n.y+c.y})) : [c]);
          return {...item,children:flattened,edges:[],width:width+28,height:y};
        }
        const owner = new Map();
        children.forEach(child => leaves(child).forEach(id => owner.set(id, child.id)));
        const seen = new Set(), edges = [];
        allEdges.forEach(edge => {
          const s = owner.get(edge.sources[0]), t = owner.get(edge.targets[0]);
          const key = s + ':' + t;
          if (s && t && s !== t && !seen.has(key)) {
            seen.add(key);
            edges.push({id: 'q' + edges.length, sources: [s], targets: [t]});
          }
        });
        const shell = {...item, children: children.map(child => ({
          id: child.id, width: child.width, height: child.height
        })), edges, layoutOptions: {...item.layoutOptions,
          'elk.hierarchyHandling': 'SEPARATE_CHILDREN'}};
        const placed = await engine.layout(shell);
        return {...placed, edges: [], children: placed.children.map(position => ({
          ...children.find(child => child.id === position.id), x: position.x, y: position.y
        }))};
      }
      result = await arrange(graph);
      // Align external systems with the actual internal nodes they communicate
      // with, not the arbitrary left/right rank of the entire cloud container.
      const cloud = result.children.find(child => child.id === '__aws_cloud');
      const external = result.children.filter(child => child !== cloud);
      if (cloud && external.length && external.every(child => !child.children)) {
        const centers = new Map();
        const collectCenters = (item, x=0, y=0) => {
          const cx = x+(item.x || 0), cy = y+(item.y || 0);
          if (item.children) item.children.forEach(child => collectCenters(child, cx, cy));
          else centers.set(item.id, [cx+item.width/2, cy+(item.iconicAnchor?37:item.height/2)]);
        };
        cloud.x = 14; cloud.y = 0;
        collectCenters(cloud);
        const desired = item => {
          const neighbors = allEdges.flatMap(edge => edge.sources[0] === item.id ? edge.targets :
            edge.targets[0] === item.id ? edge.sources : []).filter(id => centers.has(id));
          return neighbors.length ? neighbors.reduce((sum,id) => sum+centers.get(id)[0],0)/neighbors.length : 14;
        };
        external.sort((a,b) => desired(a)-desired(b));
        let cursor = 14;
        external.forEach(item => {
          item.x = Math.max(cursor, desired(item)-item.width/2); item.y = 14;
          cursor = item.x + item.width + 36;
        });
        cloud.y = 14+Math.max(...external.map(item => item.height))+48;
        result.width = Math.max(cloud.x+cloud.width+14, cursor-22);
        result.height = cloud.y+cloud.height+14;
        if (graph.externalSides) {
          const side = item => allEdges.filter(e => e.targets[0] === item.id).length >=
            allEdges.filter(e => e.sources[0] === item.id).length ? 'right' : 'left';
          const leftWidth = Math.max(0, ...external.filter(n => side(n) === 'left').map(n => n.width));
          cloud.x = leftWidth+62; cloud.y = 44;
          centers.clear(); collectCenters(cloud);
          const targetY = item => {
            const peers = allEdges.flatMap(e => e.sources[0] === item.id ? e.targets :
              e.targets[0] === item.id ? e.sources : []).filter(id => centers.has(id));
            return peers.length ? peers.reduce((sum,id) => sum+centers.get(id)[1],0)/peers.length : 44;
          };
          for (const rail of ['left','right']) {
            let y = 44;
            external.filter(n => side(n) === rail).sort((a,b) => targetY(a)-targetY(b)).forEach(item => {
              item.x = rail === 'left' ? 14 : cloud.x+cloud.width+48;
              item.y = Math.max(y, targetY(item)-item.height/2);
              y = item.y+item.height+36;
            });
          }
          result.width = Math.max(...result.children.map(n => n.x+n.width))+14;
          result.height = Math.max(...result.children.map(n => n.y+n.height))+14;
        }
      }
    } else {
      result = await engine.layout(graph);
    }
    // Python compares complete routed alternatives using readability/crossings.
    // Do not silently override its requested orientation or functional-lane layout.
    process.stdout.write(JSON.stringify(result));
  } catch (error) {
    process.stderr.write(String(error.stack || error.message));
    process.exitCode = 1;
  }
});
