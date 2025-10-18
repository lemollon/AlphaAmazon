// COMPLETE UPDATED JavaScript for index.html - Replace ALL JavaScript in your file with this:

let currentResults = [];

function startFetch() {
    const input = document.getElementById('upcInput').value.trim();
    if (!input) {
        alert('Please paste some UPCs first!');
        return;
    }

    const upcs = input.split('\n').filter(u => u.trim()).map(u => u.trim());
    
    if (upcs.length === 0) {
        alert('No valid UPCs found!');
        return;
    }

    // Disable button and show progress
    document.getElementById('fetchBtn').disabled = true;
    document.getElementById('progressSection').classList.add('active');
    document.getElementById('progressText').textContent = `Processing ${upcs.length} games...`;
    
    // Call API
    fetch('/api/process', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ upcs: upcs })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert('Error: ' + data.error);
            return;
        }

        currentResults = data.results;
        displayResults(data.results);
        displayErrors(data.errors);
        
        // Hide progress
        document.getElementById('progressSection').classList.remove('active');
        document.getElementById('fetchBtn').disabled = false;
    })
    .catch(error => {
        alert('Error processing UPCs: ' + error);
        document.getElementById('progressSection').classList.remove('active');
        document.getElementById('fetchBtn').disabled = false;
    });
}

function displayResults(results) {
    if (results.length === 0) {
        alert('No results found!');
        return;
    }

    // Update stats
    document.getElementById('totalGames').textContent = results.length;
    const profitable = results.filter(r => r.profit && r.profit > 0).length;
    document.getElementById('profitableCount').textContent = profitable;
    
    const avgProfit = results.reduce((sum, r) => sum + (r.profit || 0), 0) / results.length;
    document.getElementById('avgProfit').textContent = '
 + avgProfit.toFixed(2);
    
    const hot = results.filter(r => r.sales_rank < 1000).length;
    document.getElementById('hotItems').textContent = hot;

    // Show sections
    document.getElementById('statsSection').classList.add('active');
    document.getElementById('resultsSection').classList.add('active');

    // Populate table
    const tbody = document.getElementById('resultsBody');
    tbody.innerHTML = '';
    
    results.forEach(game => {
        const velocity = getVelocityInfo(
            game.sales_rank, 
            game.est_sales_month,
            game.velocity_category,
            game.velocity_explanation
        );
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>
                <strong>${game.title}</strong>
                ${getPriceVsAvgBadge(game)}
                ${getRiskBadge(game)}
            </td>
            <td>${game.upc}</td>
            <td>
                <strong>${game.current_price ? game.current_price.toFixed(2) : 'N/A'}</strong>
                ${game.break_even_price ? `<span class="rank-info">Break-even: ${game.break_even_price.toFixed(2)}</span>` : ''}
            </td>
            <td>${game.avg_30 ? game.avg_30.toFixed(2) : 'N/A'}</td>
            <td>${game.low_90 ? game.low_90.toFixed(2) : 'N/A'} - ${game.high_90 ? game.high_90.toFixed(2) : 'N/A'}</td>
            <td>
                <span class="velocity-badge ${velocity.badge}">${velocity.label}</span>
                <span class="rank-info" style="display: block; margin-top: 5px; font-weight: bold; color: #333;">
                    ${velocity.description}
                </span>
                <span class="rank-info" style="display: block; margin-top: 3px;">
                    Sales Rank: #${game.sales_rank.toLocaleString()}
                </span>
                <span class="rank-info" style="display: block; margin-top: 2px;">
                    Est. ${game.est_sales_per_day ? game.est_sales_per_day.toFixed(1) : Math.round(game.est_sales_month/30)} sales/day
                </span>
            </td>
            <td>
                <strong>${game.seller_count} sellers</strong>
                ${getCompetitionBadge(game)}
            </td>
            <td class="${game.profit && game.profit > 0 ? 'profit-positive' : 'profit-negative'}">
                ${game.profit ? (game.profit > 0 ? '+' : '') + '
 + game.profit.toFixed(2) : 'N/A'}
                ${game.roi_percent ? `<span class="rank-info" style="font-weight: bold;">(${game.roi_percent.toFixed(1)}% ROI)</span>` : ''}
                <span class="rank-info">@ $30 buy cost</span>
            </td>
            <td>${getOpportunityTags(game)}</td>
        `;
        tbody.appendChild(row);
    });
}

function getPriceVsAvgBadge(game) {
    if (!game.price_vs_avg_signal || !game.price_vs_avg_text) return '';
    
    const colors = {
        'excellent': '#28a745',
        'good': '#20c997',
        'neutral': '#6c757d',
        'caution': '#ffc107',
        'bad': '#dc3545'
    };
    
    const icons = {
        'excellent': '🔥',
        'good': '💚',
        'neutral': '➖',
        'caution': '⚠️',
        'bad': '🔴'
    };
    
    return `<div style="margin-top: 5px; padding: 4px 8px; background: ${colors[game.price_vs_avg_signal]}; color: white; border-radius: 4px; font-size: 11px; display: inline-block;">
        ${icons[game.price_vs_avg_signal]} ${game.price_vs_avg_text}
    </div>`;
}

function getRiskBadge(game) {
    if (!game.risk_level) return '';
    
    const bgColors = {
        'green': '#d4edda',
        'yellow': '#fff3cd',
        'orange': '#ffe5cc',
        'red': '#f8d7da'
    };
    
    const textColors = {
        'green': '#155724',
        'yellow': '#856404',
        'orange': '#cc5200',
        'red': '#721c24'
    };
    
    const riskFactorsText = game.risk_factors && game.risk_factors.length > 0 
        ? `<div style="font-size: 10px; margin-top: 3px;">• ${game.risk_factors.join('<br>• ')}</div>`
        : '';
    
    return `<div style="margin-top: 5px; padding: 6px 8px; background: ${bgColors[game.risk_color]}; color: ${textColors[game.risk_color]}; border-radius: 4px; font-size: 11px;">
        <strong>Risk: ${game.risk_score}/10 - ${game.risk_level}</strong>
        <div style="margin-top: 2px;">${game.risk_recommendation}</div>
        ${riskFactorsText}
    </div>`;
}

function getCompetitionBadge(game) {
    if (!game.competition_warning) return '';
    
    const colors = {
        'very_low': '#28a745',
        'low': '#20c997',
        'moderate': '#ffc107',
        'high': '#fd7e14',
        'very_high': '#dc3545'
    };
    
    return `<div style="margin-top: 5px; font-size: 11px; color: ${colors[game.competition_level] || '#666'}; font-weight: bold;">
        ${game.competition_warning}
    </div>`;
}

function displayErrors(errors) {
    if (!errors || errors.length === 0) {
        return;
    }

    document.getElementById('errorSection').classList.add('active');
    document.getElementById('errorCount').textContent = errors.length;
    
    const errorList = document.getElementById('errorList');
    errorList.innerHTML = '';
    
    errors.forEach(err => {
        const div = document.createElement('div');
        div.className = 'error-item';
        div.textContent = `${err.upc}: ${err.error}`;
        errorList.appendChild(div);
    });
}

function getVelocityInfo(rank, salesPerMonth, velocityCategory, velocityExplanation) {
    if (velocityExplanation) {
        const badges = {
            'lightning': 'velocity-lightning',
            'very_fast': 'velocity-fast',
            'fast': 'velocity-fast',
            'moderate': 'velocity-moderate',
            'slow': 'velocity-slow',
            'very_slow': 'velocity-slow'
        };
        
        const labels = {
            'lightning': '⚡ LIGHTNING',
            'very_fast': '🔥 VERY FAST',
            'fast': '📈 FAST',
            'moderate': '🐢 MODERATE',
            'slow': '❄️ SLOW',
            'very_slow': '🐌 VERY SLOW'
        };
        
        return {
            badge: badges[velocityCategory] || 'velocity-slow',
            label: labels[velocityCategory] || '❄️ SLOW',
            description: velocityExplanation
        };
    }
    
    if (rank < 1000) {
        return {
            badge: 'velocity-lightning',
            label: '⚡ LIGHTNING',
            description: 'LIGHTNING FAST - Sells multiple times per day. Will sell within hours.'
        };
    } else if (rank < 5000) {
        return {
            badge: 'velocity-fast',
            label: '🔥 VERY FAST',
            description: 'VERY FAST - Sells almost daily. Will sell within 1-3 days.'
        };
    } else if (rank < 20000) {
        return {
            badge: 'velocity-fast',
            label: '📈 FAST',
            description: 'FAST - Sells several times per week. Will sell within a week.'
        };
    } else if (rank < 50000) {
        return {
            badge: 'velocity-moderate',
            label: '🐢 MODERATE',
            description: 'MODERATE - Sells a few times per week. May take 1-2 weeks to sell.'
        };
    } else if (rank < 100000) {
        return {
            badge: 'velocity-slow',
            label: '❄️ SLOW',
            description: 'SLOW - Sells about once per month. May take 30+ days to sell.'
        };
    } else {
        return {
            badge: 'velocity-slow',
            label: '🐌 VERY SLOW',
            description: 'VERY SLOW - Rarely sells. May take months to sell. High risk.'
        };
    }
}

function getOpportunityTags(game) {
    let tags = '';
    
    if (game.amazon_oos) {
        tags += '<span class="tag tag-oos">🔥 Amazon OOS</span>';
    }
    
    if (game.price_vs_avg_signal === 'excellent' || game.price_vs_avg_signal === 'good') {
        tags += '<span class="tag tag-opportunity">💰 Below Avg</span>';
    }
    
    if (game.sales_rank < 5000 && game.seller_count < 5) {
        tags += '<span class="tag tag-opportunity">⚡ HOT ITEM</span>';
    }
    
    if (game.trend === 'rising') {
        tags += '<span class="tag tag-trending">📈 Rising</span>';
    }
    
    if (game.profit && game.profit > 10) {
        tags += '<span class="tag tag-opportunity">💵 High Profit</span>';
    }
    
    if (game.roi_percent && game.roi_percent > 40) {
        tags += '<span class="tag tag-opportunity">🚀 High ROI</span>';
    }
    
    if (game.competition_level === 'very_low' || game.competition_level === 'low') {
        tags += '<span class="tag tag-opportunity">✅ Low Competition</span>';
    }
    
    return tags || '—';
}

function downloadExcel() {
    if (currentResults.length === 0) {
        alert('No data to download!');
        return;
    }

    fetch('/api/download', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ results: currentResults })
    })
    .then(response => response.blob())
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `game_arbitrage_${new Date().toISOString().split('T')[0]}.xlsx`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    })
    .catch(error => {
        alert('Error downloading Excel: ' + error);
    });
}
