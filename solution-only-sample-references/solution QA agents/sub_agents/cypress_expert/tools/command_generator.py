# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Custom Command Generator - Domain-agnostic expert tool."""

from typing import Dict, Any, List


def generate_custom_commands(domain: str, domain_config: Dict[str, Any] = None) -> str:
    """Generate domain-specific custom commands without hardcoding."""

    # Basic domain analysis without domain_config dependency
    domain_analysis = {"type": "general", "complexity": "medium"}

    base_commands = _generate_base_commands()
    domain_commands = _generate_domain_specific_commands(domain, domain_analysis)
    utility_commands = _generate_utility_commands(domain_analysis)

    return f"""// cypress/support/commands.js - Expert Custom Commands
// Domain-optimized commands for {domain}

{base_commands}

{domain_commands}

{utility_commands}"""


def _generate_base_commands() -> str:
    """Generate universal base commands."""
    return """// Advanced wait strategies
Cypress.Commands.add('waitForPageLoad', () => {
    cy.get('body').should('be.visible');
    cy.window().should('have.property', 'document');
    cy.document().should('have.property', 'readyState', 'complete');
});

// Expert retry logic with exponential backoff
Cypress.Commands.add('assertWithRetry', (assertionFn, maxRetries = 3) => {
    let attempts = 0;
    
    function attempt() {
        if (attempts >= maxRetries) {
            throw new Error('Assertion failed after maximum retries');
        }
        
        try {
            assertionFn();
        } catch (error) {
            attempts++;
            const delay = Math.pow(2, attempts) * 1000; // Exponential backoff
            cy.wait(delay);
            attempt();
        }
    }
    
    attempt();
});

// Performance monitoring
Cypress.Commands.add('checkPagePerformance', (thresholds = {}) => {
    cy.window().then((win) => {
        const perfData = win.performance.getEntriesByType('navigation')[0];
        const loadTime = perfData.loadEventEnd - perfData.fetchStart;
        const threshold = thresholds.loadTime || 3000;
        expect(loadTime).to.be.lessThan(threshold);
    });
});

// Smart element interaction
Cypress.Commands.add('smartClick', (selector, options = {}) => {
    cy.get(selector)
      .should('be.visible')
      .should('not.be.disabled')
      .scrollIntoView()
      .click(options);
});

// Advanced form handling
Cypress.Commands.add('fillFormSafely', (formData) => {
    Object.entries(formData).forEach(([field, value]) => {
        if (value !== null && value !== undefined) {
            cy.get(`[data-testid="${field}"], [name="${field}"], #${field}`)
              .should('be.visible')
              .clear()
              .type(value.toString());
        }
    });
});"""


def _generate_domain_specific_commands(domain: str, analysis: Dict[str, Any]) -> str:
    """Generate commands based on domain analysis."""
    commands = []

    # Generate commands based on domain analysis patterns
    if analysis.get("payment_integration"):
        commands.append(_generate_payment_commands())

    if analysis.get("security_level") == "high":
        commands.append(_generate_security_commands())

    if analysis.get("privacy_level") == "maximum":
        commands.append(_generate_privacy_commands())

    if analysis.get("performance_critical"):
        commands.append(_generate_performance_commands())

    # Generate pattern-based commands if no specific ones
    if not commands:
        commands.append(_generate_pattern_based_commands(domain))

    return '\n'.join(commands)


def _generate_payment_commands() -> str:
    """Generate payment-related commands."""
    return """
// Payment and commerce commands
Cypress.Commands.add('clearCart', () => {
    cy.window().then((win) => {
        win.localStorage.removeItem('cart');
        win.sessionStorage.removeItem('cart');
    });
});

Cypress.Commands.add('addToCartSafely', (productId, quantity = 1) => {
    cy.get(`[data-product-id="${productId}"]`).should('be.visible');
    cy.get(`[data-product-id="${productId}"] [data-testid="add-to-cart"]`).click();
    
    if (quantity > 1) {
        cy.get('[data-testid="quantity-input"]').clear().type(quantity.toString());
    }
    
    cy.get('[data-testid="cart-count"]').should('contain', quantity);
});

Cypress.Commands.add('validateCheckoutFlow', () => {
    cy.get('[data-testid="checkout-button"]').should('be.visible').click();
    cy.url().should('include', '/checkout');
    cy.get('[data-testid="payment-form"]').should('be.visible');
});"""


def _generate_security_commands() -> str:
    """Generate security-related commands."""
    return """
// Security and authentication commands
Cypress.Commands.add('validateSecureConnection', () => {
    cy.location('protocol').should('eq', 'https:');
    cy.get('[data-testid="ssl-indicator"]').should('be.visible');
});

Cypress.Commands.add('performSecureLogin', (credentials) => {
    cy.get('[data-testid="username"]').type(credentials.username);
    cy.get('[data-testid="password"]').type(credentials.password);
    
    // Handle MFA if present
    cy.get('body').then(($body) => {
        if ($body.find('[data-testid="mfa-token"]').length > 0) {
            cy.get('[data-testid="mfa-token"]').type(credentials.mfaToken || '123456');
        }
    });
    
    cy.get('[data-testid="login-button"]').click();
    cy.url().should('not.include', '/login');
});

Cypress.Commands.add('validateSessionSecurity', () => {
    cy.window().then((win) => {
        expect(win.sessionStorage.getItem('securityToken')).to.exist;
        expect(win.localStorage.getItem('sessionId')).to.exist;
    });
});"""


def _generate_privacy_commands() -> str:
    """Generate privacy and compliance commands."""
    return """
// Privacy and compliance commands
Cypress.Commands.add('acceptPrivacyConsent', () => {
    cy.get('[data-testid="privacy-banner"]').should('be.visible');
    cy.get('[data-testid="accept-all-cookies"]').click();
    cy.get('[data-testid="privacy-banner"]').should('not.exist');
});

Cypress.Commands.add('validateDataProtection', () => {
    cy.get('[data-privacy="protected"]').each(($el) => {
        cy.wrap($el).should('have.attr', 'data-encrypted', 'true');
    });
});

Cypress.Commands.add('manageConsentPreferences', (preferences) => {
    cy.get('[data-testid="manage-cookies"]').click();
    
    Object.entries(preferences).forEach(([category, allowed]) => {
        const selector = `[data-testid="consent-${category}"]`;
        if (allowed) {
            cy.get(selector).check();
        } else {
            cy.get(selector).uncheck();
        }
    });
    
    cy.get('[data-testid="save-preferences"]').click();
});"""


def _generate_performance_commands() -> str:
    """Generate performance monitoring commands."""
    return """
// Performance monitoring commands
Cypress.Commands.add('measureLoadTime', (expectedThreshold = 2000) => {
    cy.window().then((win) => {
        const perfData = win.performance.getEntriesByType('navigation')[0];
        const loadTime = perfData.loadEventEnd - perfData.fetchStart;
        
        cy.log(`Page load time: ${loadTime}ms`);
        expect(loadTime).to.be.lessThan(expectedThreshold);
        
        return loadTime;
    });
});

Cypress.Commands.add('waitForAsyncOperations', () => {
    // Wait for pending XHR requests
    cy.window().then((win) => {
        return new Cypress.Promise((resolve) => {
            let pendingRequests = 0;
            
            const originalXHR = win.XMLHttpRequest;
            win.XMLHttpRequest = function() {
                const xhr = new originalXHR();
                pendingRequests++;
                
                xhr.addEventListener('loadend', () => {
                    pendingRequests--;
                    if (pendingRequests === 0) {
                        resolve();
                    }
                });
                
                return xhr;
            };
            
            // Fallback timeout
            setTimeout(resolve, 5000);
        });
    });
});"""


def _generate_pattern_based_commands(domain: str) -> str:
    """Generate commands based on domain name patterns."""
    domain_lower = domain.lower()

    if any(word in domain_lower for word in ['shop', 'store', 'commerce']):
        return _generate_payment_commands()
    elif any(word in domain_lower for word in ['bank', 'finance', 'payment']):
        return _generate_security_commands()
    elif any(word in domain_lower for word in ['health', 'medical', 'hospital']):
        return _generate_privacy_commands()
    else:
        return f"""
// Generic {domain} commands
Cypress.Commands.add('performDomainAction', (action, params = {{{{}}}}) => {{{{
    cy.log(`Performing ${{{domain}}} action: ${{{{action}}}}`);
    
    switch(action) {{{{
        case 'navigate':
            cy.visit(params.url || '/');
            break;
        case 'search':
            cy.get('[data-testid="search-input"]').type(params.query);
            cy.get('[data-testid="search-button"]').click();
            break;
        case 'submit':
            cy.get('[data-testid="submit-button"]').click();
            break;
        default:
            throw new Error(`Unknown action: ${{{action}}}`);
    }}
}});

Cypress.Commands.add('validateDomainState', () => {{
    cy.get('[data-testid="main-content"]').should('be.visible');
    cy.get('[data-testid="navigation"]').should('exist');
}});"""


def _generate_utility_commands(analysis: Dict[str, Any]) -> str:
    """Generate utility commands based on domain analysis."""
    utilities = ["""
// Advanced utility commands
Cypress.Commands.add('waitForStableDOM', (timeout = 5000) => {
    let lastHTML = '';
    let stableCount = 0;
    const requiredStableChecks = 3;
    
    const checkStability = () => {
        cy.get('body').then(($body) => {
            const currentHTML = $body.html();
            if (currentHTML === lastHTML) {
                stableCount++;
                if (stableCount >= requiredStableChecks) {
                    return;
                }
            } else {
                stableCount = 0;
                lastHTML = currentHTML;
            }
            
            cy.wait(500).then(checkStability);
        });
    };
    
    checkStability();
});

Cypress.Commands.add('captureFullPageScreenshot', (name) => {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    cy.screenshot(`${name}-${timestamp}`, { 
        capture: 'fullPage',
        clip: { x: 0, y: 0, width: 1280, height: 720 }
    });
});"""]

    # Add analysis-specific utilities
    if analysis.get("compliance_required"):
        utilities.append("""
Cypress.Commands.add('validateCompliance', (standards = []) => {
    standards.forEach(standard => {
        cy.get(`[data-compliance="${standard}"]`).should('exist');
    });
});""")

    if analysis.get("audit_logging"):
        utilities.append("""
Cypress.Commands.add('validateAuditTrail', () => {
    cy.window().then((win) => {
        const auditEntries = win.sessionStorage.getItem('auditTrail');
        expect(auditEntries).to.exist;
        const entries = JSON.parse(auditEntries);
        expect(entries).to.be.an('array').and.have.length.greaterThan(0);
    });
});""")

    return '\n'.join(utilities)
