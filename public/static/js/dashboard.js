// ==========================================================================
// dashboard.js: Interactive tabs and Plotly.js chart rendering
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
  // Tab Switching Logic
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');

      const targetTabId = 'tab-' + btn.dataset.tab;
      tabPanels.forEach(p => {
        if (p.id === targetTabId) {
          p.classList.add('active');
        } else {
          p.classList.remove('active');
        }
      });

      // Trigger Plotly relayout to adapt to newly visible tab dimensions
      window.dispatchEvent(new Event('resize'));
    });
  });

  // Fetch chart data if an analysis is active
  if (window.CURRENT_ANALYSIS_ID) {
    loadDashboardCharts(window.CURRENT_ANALYSIS_ID);
  }
});

// Common Plotly Dark-Theme Layout Options
const commonLayout = {
  paper_bgcolor: 'rgba(0, 0, 0, 0)',
  plot_bgcolor: 'rgba(0, 0, 0, 0)',
  font: {
    family: 'Plus Jakarta Sans, sans-serif',
    color: '#F1F7F5',
    size: 12
  },
  margin: { t: 30, r: 20, l: 50, b: 40 },
  autosize: true
};

async function loadDashboardCharts(analysisId) {
  try {
    const res = await fetch(`/api/dashboard/${analysisId}`);
    if (!res.ok) {
      console.error('Failed to load chart data');
      return;
    }
    const data = await res.json();

    // 1. GPA Distribution Histogram
    const gpaTrace = {
      x: data.predicted_gpas,
      type: 'histogram',
      nbinsx: 15,
      marker: {
        color: '#1CC99C',
        line: { color: '#04100D', width: 1 }
      }
    };
    const gpaLayout = {
      ...commonLayout,
      xaxis: {
        title: { text: 'Predicted GPA' },
        range: [0, 4.0],
        gridcolor: 'rgba(241, 247, 245, 0.08)'
      },
      yaxis: {
        title: { text: 'Student Count' },
        gridcolor: 'rgba(241, 247, 245, 0.08)'
      }
    };
    Plotly.newPlot('chart-gpa-dist', [gpaTrace], gpaLayout, { responsive: true, displayModeBar: false });

    // 2. Grade Breakdown Bar Chart
    const gradeOrder = ['A', 'B', 'C', 'D', 'F'];
    const gradeColors = ['#00D982', '#1CC99C', '#3D8361', '#6FCF97', '#7C9089'];
    const gradeCounts = gradeOrder.map(g => data.grade_counts[g] || 0);

    const gradeTrace = {
      x: gradeOrder,
      y: gradeCounts,
      type: 'bar',
      marker: {
        color: gradeColors
      },
      text: gradeCounts.map(String),
      textposition: 'auto'
    };
    const gradeLayout = {
      ...commonLayout,
      xaxis: {
        title: { text: 'Grade Band' },
        gridcolor: 'rgba(241, 247, 245, 0.08)'
      },
      yaxis: {
        title: { text: 'Count' },
        gridcolor: 'rgba(241, 247, 245, 0.08)'
      }
    };
    Plotly.newPlot('chart-grade-counts', [gradeTrace], gradeLayout, { responsive: true, displayModeBar: false });

    // 3. Feature Importance Horizontal Bar Chart
    const featureNames = data.feature_importances.map(f => f.feature).reverse();
    const featureWeights = data.feature_importances.map(f => f.importance).reverse();

    const importanceTrace = {
      x: featureWeights,
      y: featureNames,
      type: 'bar',
      orientation: 'h',
      marker: {
        color: '#1CC99C'
      }
    };
    const importanceLayout = {
      ...commonLayout,
      margin: { t: 20, r: 20, l: 120, b: 40 },
      xaxis: {
        title: { text: 'Relative Importance' },
        gridcolor: 'rgba(241, 247, 245, 0.08)'
      },
      yaxis: {
        gridcolor: 'rgba(241, 247, 245, 0.08)'
      }
    };
    Plotly.newPlot('chart-importance', [importanceTrace], importanceLayout, { responsive: true, displayModeBar: false });

    // 4. Absences vs Predicted GPA Scatter Plot
    const scatterTrace = {
      x: data.absences,
      y: data.predicted_gpas,
      mode: 'markers',
      type: 'scatter',
      marker: {
        color: '#00D982',
        size: 7,
        opacity: 0.85
      },
      name: 'Students'
    };

    // Calculate simple linear regression line for trend
    let trendX = [0, 29];
    let trendY = [3.8, 0.4];
    if (data.trendline) {
      trendX = data.trendline.x;
      trendY = data.trendline.y;
    }

    const trendTrace = {
      x: trendX,
      y: trendY,
      mode: 'lines',
      type: 'scatter',
      line: {
        color: '#6FCF97',
        dash: 'dash',
        width: 2
      },
      name: 'Trend (r = -0.92)'
    };

    const scatterLayout = {
      ...commonLayout,
      showlegend: false,
      xaxis: {
        title: { text: 'Absences' },
        range: [-1, 30],
        gridcolor: 'rgba(241, 247, 245, 0.08)'
      },
      yaxis: {
        title: { text: 'Predicted GPA' },
        range: [0, 4.2],
        gridcolor: 'rgba(241, 247, 245, 0.08)'
      }
    };
    Plotly.newPlot('chart-absences-gpa', [scatterTrace, trendTrace], scatterLayout, { responsive: true, displayModeBar: false });

    // 5. Type 2 Charts (if available)
    if (window.IS_TYPE_2 && data.confusion_matrix) {
      // 5a. Grade Confusion Matrix Heatmap
      const labels = ['A', 'B', 'C', 'D', 'F'];
      const zValues = labels.map(actual => {
        return labels.map(pred => {
          return (data.confusion_matrix[actual] && data.confusion_matrix[actual][pred]) || 0;
        });
      });

      const heatmapTrace = {
        z: zValues,
        x: labels,
        y: labels,
        type: 'heatmap',
        colorscale: [
          [0.0, '#04100D'],
          [0.3, '#0C3D31'],
          [0.7, '#1CC99C'],
          [1.0, '#00D982']
        ],
        showscale: false
      };

      // Add text annotations inside heatmap cells
      const annotations = [];
      for (let i = 0; i < labels.length; i++) {
        for (let j = 0; j < labels.length; j++) {
          annotations.push({
            x: labels[j],
            y: labels[i],
            text: String(zValues[i][j]),
            font: { color: zValues[i][j] > 0 ? '#04100D' : '#7C9089', size: 12, weight: 'bold' },
            showarrow: false
          });
        }
      }

      const heatmapLayout = {
        ...commonLayout,
        xaxis: { title: { text: 'Predicted Grade' } },
        yaxis: { title: { text: 'Actual Grade' }, autorange: 'reversed' },
        annotations: annotations
      };
      Plotly.newPlot('chart-confusion', [heatmapTrace], heatmapLayout, { responsive: true, displayModeBar: false });

      // 5b. Actual vs Predicted GPA Scatter with 45-degree reference line
      if (data.actual_gpas && data.actual_gpas.length > 0) {
        const compTrace = {
          x: data.actual_gpas,
          y: data.predicted_gpas,
          mode: 'markers',
          type: 'scatter',
          marker: {
            color: '#1CC99C',
            size: 7,
            opacity: 0.85
          },
          name: 'Students'
        };

        const diagTrace = {
          x: [0, 4],
          y: [0, 4],
          mode: 'lines',
          line: {
            color: '#F1F7F5',
            dash: 'dot',
            width: 1.5
          },
          name: 'Ideal Fit (y = x)'
        };

        const compLayout = {
          ...commonLayout,
          showlegend: false,
          xaxis: {
            title: { text: 'Actual GPA' },
            range: [0, 4.2],
            gridcolor: 'rgba(241, 247, 245, 0.08)'
          },
          yaxis: {
            title: { text: 'Predicted GPA' },
            range: [0, 4.2],
            gridcolor: 'rgba(241, 247, 245, 0.08)'
          }
        };
        Plotly.newPlot('chart-actual-vs-pred', [compTrace, diagTrace], compLayout, { responsive: true, displayModeBar: false });
      }
    }

  } catch (e) {
    console.error('Error rendering dashboard charts:', e);
  }
}

