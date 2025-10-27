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

"""Page Object Generator - Domain-agnostic expert tool."""

from typing import Dict, Any, List


def generate_page_objects(domain: str, complexity: str) -> Dict[str, str]:
    """Generate advanced Page Objects with Factory pattern - no hardcoded domains."""

    # Basic domain analysis without domain_config dependency
    domain_analysis = {"type": "general", "complexity": complexity}

    base_page = _generate_base_page(domain, complexity, domain_analysis)
    domain_page = _generate_domain_page(domain, domain_analysis)
    page_factory = _generate_page_factory(domain)

    return {
        "base_page": base_page,
        f"{domain}_page": domain_page,
        "page_factory": page_factory
    }


def _generate_base_page(domain: str, complexity: str, analysis: Dict[str, Any]) -> str:
    """Generate base page object with dynamic domain features."""

    security_features = ""
    if analysis.get("security_level") == "high":
        security_features = """
    // Enhanced security features
    validateSecureConnection() {
        cy.location('protocol').should('eq', 'https:');
        return this;
    }
    
    validateSessionSecurity() {
        cy.window().then((win) => {
            expect(win.sessionStorage.getItem('securityToken')).to.exist;
        });
        return this;
    }"""

    privacy_features = ""
    if analysis.get("privacy_level") == "maximum":
        privacy_features = """
    // Privacy and compliance features
    validateDataProtection() {
        cy.get('[data-privacy="protected"]').should('have.attr', 'data-encrypted', 'true');
        return this;
    }
    
    validateConsentManagement() {
        cy.get('[data-testid="consent-banner"]').should('be.visible');
        return this;
    }"""

    performance_features = ""
    if analysis.get("performance_critical"):
        performance_features = """
    // Performance optimization features
    measurePagePerformance() {
        cy.window().then((win) => {
            const perfData = win.performance.getEntriesByType('navigation')[0];
            const loadTime = perfData.loadEventEnd - perfData.fetchStart;
            expect(loadTime).to.be.lessThan(2000); // Strict performance for critical domains
        });
        return this;
    }"""

    return f"""// base-page.js - Expert Page Object Base Class
// Domain: {domain} | Complexity: {complexity}
// Generated dynamically based on domain analysis

export class BasePage {{
    constructor() {{
        this.url = '';
        this.pageElements = {{}};
        this.domain = '{domain}';
        this.domainAnalysis = {analysis};
    }}

    // Expert navigation with domain-specific validations
    visit(path = '') {{
        cy.visit(this.url + path);
        this.waitForPageLoad();
        this.validateDomainSpecificElements();
        return this;
    }}

    waitForPageLoad() {{
        cy.get('body').should('be.visible');
        cy.window().should('have.property', 'document');
        
        // Domain-specific loading validation
        this.waitForDomainSpecificLoading();
    }}

    validateDomainSpecificElements() {{
        // Dynamic validation based on domain analysis
        if (this.domainAnalysis.compliance_required) {{
            this.validateComplianceElements();
        }}
        
        if (this.domainAnalysis.security_level) {{
            this.validateSecurityElements();
        }}
        
        if (this.domainAnalysis.privacy_level) {{
            this.validatePrivacyElements();
        }}
    }}

    waitForDomainSpecificLoading() {{
        // Smart loading detection based on domain type
        const loadingIndicators = this.getDomainLoadingIndicators();
        
        loadingIndicators.forEach(indicator => {{
            cy.get(indicator).should('not.exist');
        }});
    }}

    getDomainLoadingIndicators() {{
        // Dynamic loading indicators based on domain patterns
        const indicators = ['[data-testid="loading"]', '.spinner'];
        
        if (this.domain.includes('shop') || this.domain.includes('commerce')) {{
            indicators.push('[data-testid="product-loading"]', '[data-testid="cart-loading"]');
        }}
        
        if (this.domain.includes('bank') || this.domain.includes('finance')) {{
            indicators.push('[data-testid="balance-loading"]', '[data-testid="transaction-loading"]');
        }}
        
        return indicators;
    }}

    // Expert error handling
    handleErrors() {{
        cy.window().then((win) => {{
            win.addEventListener('error', (e) => {{
                throw new Error(`Page error in {{this.domain}}: ${{e.message}}`);
            }});
        }});
        return this;
    }}{security_features}{privacy_features}{performance_features}
}}"""


def _generate_domain_page(domain: str, analysis: Dict[str, Any]) -> str:
    """Generate domain-specific page object."""

    elements = _generate_dynamic_elements(domain, analysis)

    element_definitions = _format_elements(elements)
    methods = _generate_dynamic_methods(domain, elements, analysis)

    return f"""// {domain.replace('-', '_')}-page.js - Domain-Specific Page Object
import {{ BasePage }} from './base-page';

export class {domain.replace('-', '').title()}Page extends BasePage {{
    constructor() {{
        super();
        {element_definitions}
    }}

    {methods}

    // Expert business rule validation
    validateBusinessRules(testData) {{
        // Dynamic business rule validation based on domain analysis
        this.validateDataIntegrity(testData);
        
        if (this.domainAnalysis.compliance_required) {{
            this.validateComplianceRules(testData);
        }}
        
        if (this.domainAnalysis.security_level === 'high') {{
            this.validateSecurityRules(testData);
        }}
    }}

    validateDataIntegrity(testData) {{
        // Generic data integrity checks
        if (testData.amount && typeof testData.amount === 'number') {{
            expect(testData.amount).to.be.greaterThan(0);
        }}
        
        if (testData.email) {{
            expect(testData.email).to.match(/^[^@]+@[^@]+\\.[^@]+$/);
        }}
    }}

    validateComplianceRules(testData) {{
        // Dynamic compliance validation
        cy.get('[data-compliance="required"]').should('be.visible');
        
        if (this.domainAnalysis.audit_logging) {{
            cy.get('[data-testid="audit-trail"]').should('exist');
        }}
    }}

    validateSecurityRules(testData) {{
        // Dynamic security validation
        if (testData.sensitiveData) {{
            cy.get('[data-sensitive="true"]').should('have.attr', 'data-encrypted', 'true');
        }}
    }}
}}"""


def _generate_dynamic_elements(domain: str, analysis: Dict[str, Any]) -> Dict[str, str]:
    """Generate elements based on domain analysis."""
    elements = {
        "mainContent": '[data-testid="main-content"]',
        "navigation": '[data-testid="navigation"]',
        "footer": '[data-testid="footer"]'
    }

    # Add domain-specific elements based on analysis
    if analysis.get("payment_integration"):
        elements.update({
            "cartIcon": '[data-testid="cart-icon"]',
            "checkoutBtn": '[data-testid="checkout-button"]',
            "paymentForm": '[data-testid="payment-form"]'
        })

    if analysis.get("security_level") == "high":
        elements.update({
            "secureIndicator": '[data-testid="secure-indicator"]',
            "logoutBtn": '[data-testid="secure-logout"]',
            "mfaInput": '[data-testid="mfa-input"]'
        })

    if analysis.get("privacy_level") == "maximum":
        elements.update({
            "privacyNotice": '[data-testid="privacy-notice"]',
            "consentForm": '[data-testid="consent-form"]',
            "dataControls": '[data-testid="data-controls"]'
        })

    return elements


def _format_elements(elements: Dict[str, str]) -> str:
    """Format elements dictionary as JavaScript object."""
    if not elements:
        return "this.elements = {};"
    formatted_elements = []
    for key, value in elements.items():
        formatted_elements.append(f"            {key}: '{value}'")

    elements_str = ',\n'.join(formatted_elements)
    return f"""this.elements = {{
{elements_str}
        }};"""


def _generate_dynamic_methods(domain: str, elements: Dict[str, str], analysis: Dict[str, Any]) -> str:
    """Generate methods based on available elements and domain analysis."""
    methods = []

    # Generate methods based on available elements
    if "cartIcon" in elements and "checkoutBtn" in elements:
        methods.append("""    // Commerce-specific methods
    addToCart() {
        cy.get(this.elements.addToCartBtn).click();
        return this;
    }

    proceedToCheckout() {
        cy.get(this.elements.cartIcon).click();
        cy.get(this.elements.checkoutBtn).click();
        return this;
    }""")

    if "secureIndicator" in elements:
        methods.append("""    // Security-specific methods
    validateSecureSession() {
        cy.get(this.elements.secureIndicator).should('be.visible');
        return this;
    }

    performSecureLogout() {
        cy.get(this.elements.logoutBtn).click();
        cy.url().should('include', '/login');
        return this;
    }""")

    if "consentForm" in elements:
        methods.append("""    // Privacy-specific methods
    acceptConsent() {
        cy.get(this.elements.consentForm).find('[data-testid="accept-btn"]').click();
        return this;
    }

    managePrivacySettings() {
        cy.get(this.elements.dataControls).click();
        return this;
    }""")

    # Add generic methods if no specific ones were generated
    if not methods:
        methods.append(f"""    // Generic {domain} methods
    performMainAction() {{
        cy.get(this.elements.mainContent).should('be.visible');
        return this;
    }}

    validatePageElements() {{
        Object.values(this.elements).forEach(selector => {{
            cy.get(selector).should('exist');
        }});
        return this;
    }}""")

    return '\n\n'.join(methods)


def _generate_page_factory(domain: str) -> str:
    """Generate Page Factory pattern."""
    return f"""// page-factory.js - Expert Page Factory Pattern
import {{ {domain.replace('-', '').title()}Page }} from './{domain}-page';

export class PageFactory {{
    static create(pageType, options = {{}}) {{
        switch(pageType) {{
            case '{domain}':
                return new {domain.replace('-', '').title()}Page(options);
            default:
                throw new Error(`Unknown page type: ${{pageType}}`);
        }}
    }}

    // Expert page creation with domain optimization
    static createOptimized(pageType, domain = '{domain}') {{
        const page = this.create(pageType);
        page.setupDomainOptimizations(domain);
        return page;
    }}

    // Dynamic page creation based on URL patterns
    static createFromUrl(url) {{
        const domain = this.extractDomainFromUrl(url);
        return this.create(domain);
    }}

    static extractDomainFromUrl(url) {{
        // Extract domain context from URL
        const urlParts = new URL(url).pathname.split('/');
        return urlParts[1] || '{domain}';
    }}
}}"""
