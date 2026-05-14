// hydraulic.js - EPANET physics integration and stochastic demand generation

const epanetId = (id) => String(id).replace(/\s+/g, '_');

export function syncHydraulicInputs(project, systemData, simTimeMinutes) {
    if (!project) return;
    systemData.nodes.forEach(n => {
        if (n.type === 'Tank') {
            const head = (n.elevation ?? 0) + ((n.level ?? 0) / 100) * (n.maxLevel ?? 20);
            try {
                const idx = project.getNodeIndex(epanetId(n.id));
                project.setNodeValue(idx, 0, head); // 0 is EN_ELEVATION for reservoirs
            } catch (e) { /* ignore disconnected node */ }
        } else if (n.type === 'PressureBoundary') {
            let liveHead = n.head ?? 100;
            if (n.pattern && systemData.patterns) {
                const pat = systemData.patterns.find(p => p.id === n.pattern);
                if (pat && pat.multipliers && pat.multipliers.length === 24) {
                    const currentHourIndex = Math.floor(simTimeMinutes / 60) % 24;
                    const multiplier = pat.multipliers[currentHourIndex] ?? 1.0;
                    liveHead *= multiplier;
                }
            }
            n._liveHead = liveHead;
            try {
                const idx = project.getNodeIndex(epanetId(n.id));
                project.setNodeValue(idx, 0, liveHead);
            } catch (e) {}
        }
    });
}

function randNorm() {
    let u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
}

function isNodeIsolated(nodeId, systemData, map) {
    const connected = systemData.links.filter(l => l.from === nodeId || l.to === nodeId);
    if (connected.length === 0) return true; // no connections → nowhere to go
    return connected.every(l => {
        const fromNode = map[l.from];
        const toNode   = map[l.to];
        if (fromNode && fromNode.type === 'Pump')  return (fromNode._currentSpeed ?? (fromNode.status === 'ON' ? 100 : 0)) <= 0;
        if (toNode   && toNode.type   === 'Pump')  return (toNode._currentSpeed ?? (toNode.status === 'ON' ? 100 : 0)) <= 0;
        if (fromNode && fromNode.type === 'Valve') return (fromNode._currentSetting ?? (fromNode.status !== 'Closed' ? 100 : 0)) <= 0;
        if (toNode   && toNode.type   === 'Valve') return (toNode._currentSetting ?? (toNode.status !== 'Closed' ? 100 : 0)) <= 0;
        if (fromNode && fromNode.type === 'Turbine') return (fromNode._currentSetting ?? (fromNode.status === 'ON' ? 100 : 0)) <= 0;
        if (toNode   && toNode.type   === 'Turbine') return (toNode._currentSetting ?? (toNode.status === 'ON' ? 100 : 0)) <= 0;
        return false; // plain pipe with no pump/valve at either end → open
    });
}

export function calculateStochasticDemand(systemData, simTimeMinutes, simSpeed, map) {
    systemData.nodes.forEach(n => {
        if ((n.type === 'InflowNode' || n.type === 'OutflowNode') && n.randomFlow) {
            // Only update demand at the same frequency as the chart (0.05 sim minutes)
            // so the UI numbers don't flicker crazily between chart updates
            if (n._lastDemandSimTime === undefined || simTimeMinutes - n._lastDemandSimTime >= 0.05) {
                const mu  = n.demand ?? 10;
                const sd  = n.rngStd   ?? 2;
                const baseAC = Math.max(0.001, Math.min(0.999, n.rngAC ?? 0.8));
                const phi = Math.max(0.001, Math.min(0.999, Math.pow(baseAC, simSpeed / 10)));

                const prev = n._arDemand ?? mu;

                const epsilon    = sd * Math.sqrt(1 - phi * phi) * randNorm();
                const nextDemand = phi * prev + (1 - phi) * mu + epsilon;
                n._arDemand      = Math.max(0, nextDemand);
                n._baseLiveDemand = n._arDemand;
                n._lastDemandSimTime = simTimeMinutes;
            }
            n._liveDemand = n._baseLiveDemand ?? (n.demand ?? 10);
        } else if (n.type === 'InflowNode' || n.type === 'OutflowNode') {
            n._liveDemand = n.demand ?? 10;
        }

        if ((n.type === 'InflowNode' || n.type === 'OutflowNode') && n.pattern && systemData.patterns) {
            const pat = systemData.patterns.find(p => p.id === n.pattern);
            if (pat && pat.multipliers && pat.multipliers.length === 24) {
                const currentHourIndex = Math.floor(simTimeMinutes / 60) % 24;
                const multiplier = pat.multipliers[currentHourIndex] ?? 1.0;
                n._liveDemand *= multiplier;
            }
        }

        if ((n.type === 'InflowNode' || n.type === 'OutflowNode') && isNodeIsolated(n.id, systemData, map)) {
            n._liveDemand = 0;
            return;
        }

        if (n.type === 'InflowNode' || n.type === 'OutflowNode') {
            const connectedLinks = systemData.links.filter(l => l.from === n.id || l.to === n.id);
            connectedLinks.forEach(l => {
                const otherId = l.from === n.id ? l.to : l.from;
                const other   = map[otherId];
                if (other && other.type === 'Pump') {
                    const currentSpeed = other._currentSpeed !== undefined ? other._currentSpeed : (other.status === 'ON' ? (other.setting ?? 100) : 0);
                    const speedRatio = Math.max(0, Math.min(1, currentSpeed / 100));
                    n._liveDemand = (n._liveDemand ?? 0) * speedRatio;
                }
            });
        }
        if (n.type === 'InflowNode' || n.type === 'OutflowNode') {
            n._intendedDemand = n._liveDemand;
        }
    });
}
export function applyComponentRamps(systemData, simSpeedMinutes, poweredNodes, enforcePowerTopology, forceInstant = false) {
    systemData.nodes.forEach(node => {
        if (node.type === 'Pump') {
            const hasPower = !enforcePowerTopology || poweredNodes.has(node.id);
            const actualStatus = node._surgeOverride || node.status;
            const isON = actualStatus === 'ON' && hasPower;
            
            const targetSpeed = isON ? (node.pumpType === 'Variable' ? (node._targetSetting ?? node.setting ?? 100) : 100) : 0;
            
            if (node._currentSpeed === undefined || forceInstant) {
                node._currentSpeed = targetSpeed;
            }
            
            if (!forceInstant && node._currentSpeed !== targetSpeed) {
                const rampTimeMinutes = (node.rampTime ?? 5) / 60;
                if (rampTimeMinutes <= 0) {
                    node._currentSpeed = targetSpeed;
                } else {
                    const step = (100 / rampTimeMinutes) * simSpeedMinutes;
                    if (node._currentSpeed < targetSpeed) {
                        node._currentSpeed = Math.min(targetSpeed, node._currentSpeed + step);
                    } else {
                        node._currentSpeed = Math.max(targetSpeed, node._currentSpeed - step);
                    }
                }
            }
        } else if (node.type === 'Valve' || node.type === 'Turbine') {
            const actualStatus = node._surgeOverride || node.status;
            const isON = node.type === 'Valve' ? actualStatus !== 'Closed' : actualStatus === 'ON';
            const targetSetting = isON ? (node._targetSetting ?? node.setting ?? 100) : 0;
            
            if (node._currentSetting === undefined || forceInstant) {
                node._currentSetting = targetSetting;
            }
            
            if (!forceInstant && node._currentSetting !== targetSetting) {
                const strokeTimeMinutes = (node.type === 'Turbine' ? (node.rampTime ?? 10) : (node.strokeTime ?? 10)) / 60;
                if (strokeTimeMinutes <= 0) {
                    node._currentSetting = targetSetting;
                } else {
                    let step = (100 / strokeTimeMinutes) * simSpeedMinutes;
                    
                    // Slower stroke near 0% (2-stage effect for equal percentage valves)
                    if (node._currentSetting < 20) {
                        step = step * Math.max(0.1, node._currentSetting / 20);
                    }
                    
                    if (node._currentSetting < targetSetting) {
                        node._currentSetting = Math.min(targetSetting, node._currentSetting + step);
                    } else {
                        node._currentSetting = Math.max(targetSetting, node._currentSetting - step);
                    }
                }
            }
        }
    });
}

export function syncHydraulicControls(project, systemData, map, poweredNodes, enforcePowerTopology) {
    if (!project) return;
    // Sync regular links (pipes)
    systemData.links.forEach(l => {
        try {
            const idx = project.getLinkIndex(l._epanetId || l.id);
            let forceClose = false;
            project.setLinkValue(idx, 11, forceClose ? 0 : 1);
        } catch (e) { /* ignore */ }
    });

    // Sync composite nodes (Pumps, Valves, Turbines) using their dedicated links
    systemData.nodes.forEach(n => {
        if (n.type === 'Pump' || n.type === 'Valve' || n.type === 'Turbine') {
            try {
                const linkId = `${epanetId(n.id)}_link`;
                const idx = project.getLinkIndex(linkId);
                let forceClose = false;
                
                if (n.type === 'Pump') {
                    const isON = (n._currentSpeed > 0) && !forceClose;
                    project.setLinkValue(idx, 11, isON ? 1 : 0); // 11 is EN_STATUS
                    if (isON) {
                        const speed = Math.max(0, n._currentSpeed) / 100;
                        project.setLinkValue(idx, 12, speed); // 12 is EN_SETTING for pump speed
                    } else {
                        project.setLinkValue(idx, 12, 0.0); // Force speed to 0 when OFF
                    }
                } else if (n.type === 'Valve') {
                    if ((n._currentSetting || 0) <= 0 || forceClose) {
                        project.setLinkValue(idx, 11, 0); // CLOSE
                    } else {
                        project.setLinkValue(idx, 11, 1); // OPEN
                        // Map setting (1-100) to Minor Loss K factor (0 to 10000)
                        const setting = Math.max(1, n._currentSetting);
                        const K = Math.pow(100 / setting, 2) - 1;
                        project.setLinkValue(idx, 3, K); // 3 is EN_MINORLOSS for Pipes
                    }
                } else if (n.type === 'Turbine') {
                    if (n.status === 'OFF' || forceClose) {
                        project.setLinkValue(idx, 11, 0); // CLOSE
                    } else {
                        project.setLinkValue(idx, 11, 1); // OPEN
                        
                        const Q_d = n.designFlow ?? 100;
                        const H_d = n.designHead ?? 50;
                        const diam = 8; // Dummy pipe diameter
                        const A = Math.PI * Math.pow(diam / 24, 2); // Area in sq ft
                        
                        // V_d is velocity in ft/s at design flow (GPM)
                        const V_d = Q_d / (A * 448.831);
                        
                        // K_base is the minor loss coefficient required to drop H_d feet at V_d
                        const K_base = (H_d * 64.4) / Math.pow(V_d > 0.001 ? V_d : 0.001, 2);
                        
                        const setting = Math.max(1, n._targetSetting ?? n.setting ?? 100);
                        const K = K_base / Math.pow(setting / 100, 2);
                        
                        project.setLinkValue(idx, 3, K); // 3 is EN_MINORLOSS
                    }
                }
            } catch (e) {}
        }
    });

    systemData.nodes.forEach(n => {
        if ((n.type === 'InflowNode' || n.type === 'OutflowNode') && n._liveDemand !== undefined) {
            try {
                const idx = project.getNodeIndex(epanetId(n.id));
                const epanetDemand = n.type === 'InflowNode' ? -n._liveDemand : n._liveDemand;
                project.setNodeValue(idx, 1, epanetDemand); // 1 = EN_BASEDEMAND
            } catch (e) { /* node may not exist in current EPANET model */ }
        }
    });
}

export function solveHydraulics(project, systemData, simSpeed) {
    if (!project) return;
    project.runH();

    if (systemData.wqEnabled && systemData.wqType && systemData.wqType !== 'None') {
        try {
            project.setTimeParameter(10, simSpeed * 60); // 10 is EN_QUALSTEP
            let t = 0;
            project.runQ(t);
            project.stepQ();
            
            systemData.nodes.forEach(n => {
                try {
                    const idx = project.getNodeIndex(epanetId(n.id));
                    n.quality = Number(project.getNodeValue(idx, 10)); // 10 is EN_QUALITY
                } catch(e) {
                    n.quality = 0;
                }
            });
        } catch(e) {
            // Silent catch to prevent crashing the sim if WQ fails
        }
    }
}

export function extractHydraulicResults(project, systemData, simSpeed, map) {
    if (!project) return;

    // 1. Extract raw flows from EPANET
    systemData.links.forEach(l => {
        try {
            const idx = project.getLinkIndex(l._epanetId || l.id);
            const raw = project.getLinkValue(idx, 8); // 8 is EN_FLOW
            l.flowGPM = Math.abs(raw) < 1e-10 ? 0 : Number(raw);
        } catch (e) {
            const sibling = systemData.links.find(
                other => other !== l && other.from === l.from && other.to === l.to
            );
            l.flowGPM = sibling ? (sibling.flowGPM ?? 0) : 0;
        }
    });

    // 2. Enforce strict mass balance bounds on Tanks with network propagation
    let maxDiff = 1;
    let iters = 0;
    while (maxDiff > 0.01 && iters < 20) {
        maxDiff = 0;
        systemData.nodes.forEach(n => {
            let linkIn = 0;
            let linkOut = 0;
            
            systemData.links.forEach(l => {
                if (l.to === n.id) {
                    if (l.flowGPM >= 0) linkIn += l.flowGPM;
                    else linkOut += Math.abs(l.flowGPM);
                } else if (l.from === n.id) {
                    if (l.flowGPM >= 0) linkOut += l.flowGPM;
                    else linkIn += Math.abs(l.flowGPM);
                }
            });

            // For InflowNode, demand is negative in EPANET, but in JS n._liveDemand is positive supply
            const extIn = (n.type === 'InflowNode') ? (n._liveDemand ?? 0) : 0;
            const extOut = (n.type === 'OutflowNode') ? (n._liveDemand ?? 0) : 0;
            
            const totalSupply = linkIn + extIn;
            const totalDemand = linkOut + extOut;

            if (n.type === 'Tank') {
                if ((n.level ?? 50) <= 0.01 && totalDemand > totalSupply) {
                    const ratio = totalSupply / totalDemand;
                    systemData.links.forEach(l => {
                        if ((l.from === n.id && l.flowGPM > 0) || (l.to === n.id && l.flowGPM < 0)) {
                            const oldFlow = l.flowGPM; l.flowGPM *= ratio;
                            maxDiff = Math.max(maxDiff, Math.abs(oldFlow - l.flowGPM));
                        }
                    });
                } else if ((n.level ?? 50) >= 99.99 && totalSupply > totalDemand) {
                    const ratio = totalDemand / totalSupply;
                    systemData.links.forEach(l => {
                        if ((l.to === n.id && l.flowGPM > 0) || (l.from === n.id && l.flowGPM < 0)) {
                            const oldFlow = l.flowGPM; l.flowGPM *= ratio;
                            maxDiff = Math.max(maxDiff, Math.abs(oldFlow - l.flowGPM));
                        }
                    });
                }
            } else if (n.type === 'Junction' || n.type === 'InflowNode' || n.type === 'OutflowNode') {
                if (Math.abs(totalSupply - totalDemand) > 0.01) {
                    if (totalSupply < totalDemand && totalDemand > 0) {
                        const ratio = totalSupply / totalDemand;
                        systemData.links.forEach(l => {
                            if ((l.from === n.id && l.flowGPM > 0) || (l.to === n.id && l.flowGPM < 0)) {
                                const oldFlow = l.flowGPM; l.flowGPM *= ratio;
                                maxDiff = Math.max(maxDiff, Math.abs(oldFlow - l.flowGPM));
                            }
                        });
                        if (n.type === 'OutflowNode') {
                            const oldExt = n._liveDemand; n._liveDemand *= ratio;
                            maxDiff = Math.max(maxDiff, Math.abs(oldExt - n._liveDemand));
                        }
                    } else if (totalDemand < totalSupply && totalSupply > 0) {
                        const ratio = totalDemand / totalSupply;
                        systemData.links.forEach(l => {
                            if ((l.to === n.id && l.flowGPM > 0) || (l.from === n.id && l.flowGPM < 0)) {
                                const oldFlow = l.flowGPM; l.flowGPM *= ratio;
                                maxDiff = Math.max(maxDiff, Math.abs(oldFlow - l.flowGPM));
                            }
                        });
                        if (n.type === 'InflowNode') {
                            const oldExt = n._liveDemand; n._liveDemand *= ratio;
                            maxDiff = Math.max(maxDiff, Math.abs(oldExt - n._liveDemand));
                        }
                    }
                }
            }
        });
        iters++;
    }

    // 3. Extract headloss and compute component-specific physics for pipes
    systemData.links.forEach(l => {
        // Nothing special to do here for pipes, flow was extracted above
    });

    // Extract composite node physics
    systemData.nodes.forEach(n => {
        if (n.type === 'Pump' || n.type === 'Valve' || n.type === 'Turbine') {
            try {
                const linkId = `${epanetId(n.id)}_link`;
                const idx = project.getLinkIndex(linkId);
                
                const rawQ = project.getLinkValue(idx, 8);
                const flowGPM = Math.abs(rawQ) < 1e-10 ? 0 : Number(rawQ);
                n._flowGPM = flowGPM;

                if (n.type === 'Pump') {
                    const rawH = project.getLinkValue(idx, 10); // 10 is EN_HEADLOSS
                    n._tdh   = Math.abs(rawH);
                    const Q_d = n.designFlow ?? 100;
                    const H_d = n.designHead ?? 50;
                    const Eff_d = n.efficiency ?? 75;
                    const N = Math.max(0.01, (n._currentSpeed ?? (n.status === 'ON' ? (n.setting ?? 100) : 0)) / 100);
                    const isRunning = (n._currentSpeed !== undefined ? n._currentSpeed > 0 : n.status === 'ON');
                    
                    let effDecimal = 0;
                    if (isRunning && flowGPM > 0) {
                        const qRatio = (flowGPM / N) / Q_d;
                        effDecimal = (Eff_d / 100) * (2 * qRatio - Math.pow(qRatio, 2));
                        effDecimal = Math.max(0.05, Math.min(1.0, effDecimal)) * N;
                    }

                    n._efficiency = isRunning && flowGPM > 0 ? effDecimal * 100 : 0;
                    
                    let fluidPower = isRunning && flowGPM > 0 ? (flowGPM * n._tdh) / (3960 * (effDecimal || 1)) : 0;
                    let deadheadPower = 0;
                    if (isRunning) {
                        deadheadPower = ((Q_d * H_d) / (3960 * (Eff_d / 100))) * 0.4 * Math.pow(N, 3);
                    }
                    n._power = isRunning ? Math.max(fluidPower, deadheadPower) : 0;

                    let kW = n._power * 0.7457;

                    // Apply electrical inrush multiplier during acceleration
                    const targetSpeed = n.status === 'ON' ? (n.setting ?? 100) : 0;
                    if (isRunning && n._currentSpeed !== undefined && n._currentSpeed < targetSpeed && n._currentSpeed > 0) {
                        let inrushMult = 1.0;
                        if (n.pumpType === 'Variable') {
                            inrushMult = 1.2;
                        } else {
                            const method = n.startMethod || 'DOL';
                            if (method === 'DOL') inrushMult = 6.0;
                            else if (method === 'SoftStarter') inrushMult = 3.0;
                        }
                        // Base inrush on approximate full load power
                        const flaPowerKW = ((Q_d * H_d) / (3960 * (Eff_d / 100))) * 0.7457;
                        kW = flaPowerKW * inrushMult;
                    }

                    n._powerKW = kW;
                    n._peakPowerKW = Math.max(n._peakPowerKW ?? 0, kW);

                    const simHoursThisTick = simSpeed / 60; // simSpeed is sim-minutes per tick
                    n._energyKWh = (n._energyKWh ?? 0) + kW * simHoursThisTick;
                } else if (n.type === 'Turbine') {
                    const rawH = project.getLinkValue(idx, 10); // 10 is EN_HEADLOSS
                    n._headLoss = Math.abs(rawH);
                    const Q_d = n.designFlow ?? 100;
                    const Eff_d = n.efficiency ?? 80;
                    const N = Math.max(0.01, (n._currentSetting ?? (n.status === 'ON' ? (n.setting ?? 100) : 0)) / 100);
                    const isRunning = (n._currentSetting !== undefined ? n._currentSetting > 0 : n.status === 'ON');
                    
                    let effDecimal = 0;
                    if (isRunning && flowGPM > 0) {
                        const qRatio = (flowGPM / N) / Q_d;
                        effDecimal = (Eff_d / 100) * (2 * qRatio - Math.pow(qRatio, 2));
                        effDecimal = Math.max(0.05, Math.min(1.0, effDecimal)) * N;
                    }
                    
                    n._efficiency = isRunning && flowGPM > 0 ? effDecimal * 100 : 0;
                    
                    // Calculate power generated: kW = (Flow * Headloss) / 3960 * Efficiency
                    let kW = 0;
                    if (isRunning && flowGPM > 0) {
                        n._power = (flowGPM * (n._headLoss * Math.pow(N, 2))) / 3960 * (effDecimal || 1);
                        kW = n._power * 0.7457;
                    } else {
                        n._power = 0;
                    }
                    
                    n._powerKW = kW;
                    n._peakPowerKW = Math.max(n._peakPowerKW ?? 0, kW);
                    
                    const simHoursThisTick = simSpeed / 60;
                    n._cumulativeEnergyKWh = (n._cumulativeEnergyKWh ?? 0) + kW * simHoursThisTick;
                } else if (n.type === 'Valve') {
                    const rawH = project.getLinkValue(idx, 10); // 10 is EN_HEADLOSS
                    n._headLoss = Math.abs(rawH);
                }
            } catch (e) {}
        }
    });

    systemData.nodes.forEach(n => {
        if ((n.type === 'InflowNode' || n.type === 'OutflowNode') && n._liveDemand === 0) {
            systemData.links.forEach(l => {
                if (l.from === n.id || l.to === n.id) l.flowGPM = 0;
            });
        }
    });

    // Extract EPANET Node pressures for all nodes
    systemData.nodes.forEach(n => {
        if (n.type === 'Pump' || n.type === 'Valve' || n.type === 'Turbine') {
            try {
                const inIdx = project.getNodeIndex(`${epanetId(n.id)}_in`);
                n._upstreamPressure = Number(project.getNodeValue(inIdx, 11));
            } catch (e) {
                n._upstreamPressure = 0;
            }
            try {
                const outIdx = project.getNodeIndex(`${epanetId(n.id)}_out`);
                n._downstreamPressure = Number(project.getNodeValue(outIdx, 11));
            } catch (e) {
                n._downstreamPressure = 0;
            }
            // For the single component node tooltip backward compatibility (if used), just set it to upstream
            n._pressure = n._upstreamPressure;
        } else {
            try {
                const idx = project.getNodeIndex(epanetId(n.id));
                const rawP = project.getNodeValue(idx, 11);
                n._pressure = Number(rawP);
            } catch (e) {
                n._pressure = 0;
            }
        }
    });

    integrateMassBalance(systemData, simSpeed, map);
}

export function integrateMassBalance(systemData, simSpeed, map) {
    // Apply flows to Tank levels
    systemData.nodes.forEach(n => {
        if (n.type === 'Tank') {
            let finalNetQ = 0;
            systemData.links.forEach(l => {
                if (l.to === n.id) finalNetQ += l.flowGPM;
                if (l.from === n.id) finalNetQ -= l.flowGPM;
            });
            const netGallons = finalNetQ * simSpeed; // simSpeed is minutes/tick
            const netCuFt = netGallons / 7.48052; // convert gallons to cubic feet
            
            const d = n.diameter ?? 50;
            const r = d / 2;
            const areaCuFt = Math.PI * r * r;
            
            const levelChangeFt = areaCuFt > 0 ? (netCuFt / areaCuFt) : 0;
            const maxLevelFt = n.maxLevel ?? 20;
            
            const levelChangePct = maxLevelFt > 0 ? (levelChangeFt / maxLevelFt) * 100 : 0;
            
            n.level = Math.max(0, Math.min(100, n.level + levelChangePct));
        }
    });

    // Legacy Chiller demo (only if Chiller node exists)
    const chiller = map['Chiller'];
    if (chiller) {
        const ahus   = ['AHU-1','AHU-2','AHU-3'].map(id => map[id]).filter(Boolean);
        const pump   = map['CHW-P1'];
        const pumpOn = pump && pump.status === 'ON';
        ahus.forEach((ahu, i) => {
            const load    = [0.4, 0.3, 0.5][i] * simSpeed;
            const cooling = pumpOn ? 0.7 * simSpeed : 0;
            ahu.level = Math.max(0, Math.min(100, ahu.level - load + cooling));
        });
        const chillerLoad     = pumpOn ? 0.6 * simSpeed : 0;
        const chillerRecovery = 0.2 * simSpeed;
        chiller.level = Math.max(0, Math.min(100, chiller.level - chillerLoad + chillerRecovery));
    }

    systemData.nodes.forEach(n => {
        if (n.type === 'InflowNode' || n.type === 'OutflowNode') {
            n._cumulativeFlowVol = (n._cumulativeFlowVol || 0) + ((n._liveDemand ?? 0) * simSpeed);
        }
    });
}
