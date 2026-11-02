// =============================================================================
// Scenario B — first-boot configuration.
//
// Disables anonymous access, creates the lab administrator from the
// environment (JENKINS_ADMIN_ID / JENKINS_ADMIN_PASSWORD), and keeps the
// instance URL stable. The job itself is created by scripts/jenkins-bootstrap.sh
// so its config is versioned in the repository.
// =============================================================================
import jenkins.model.Jenkins
import hudson.security.HudsonPrivateSecurityRealm
import hudson.security.FullControlOnceLoggedInAuthorizationStrategy

def instance = Jenkins.get()

def adminId = System.getenv("JENKINS_ADMIN_ID") ?: "securityadmin"
def adminPassword = System.getenv("JENKINS_ADMIN_PASSWORD")
if (adminPassword) {
    def realm = new HudsonPrivateSecurityRealm(false)
    if (realm.getUser(adminId) == null) {
        realm.createAccount(adminId, adminPassword)
    }
    instance.setSecurityRealm(realm)

    def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
    strategy.setAllowAnonymousRead(false)
    instance.setAuthorizationStrategy(strategy)
    instance.save()
    println("[init] security realm configured for ${adminId}")
} else {
    println("[init] JENKINS_ADMIN_PASSWORD not set; leaving anonymous access")
}
