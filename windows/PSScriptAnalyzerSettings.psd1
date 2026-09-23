# PSScriptAnalyzer settings. `verify.py` passes this file explicitly.
#
# windows/powershell/*.ps1 is an interactive shell profile, not a shipped
# module. Setting globals, writing colour to the console, and eval-ing a tool's
# own init snippet is the job here, so the module-shaped rules below are off.
# Security and correctness rules stay on.
@{
    Severity     = @('Error', 'Warning')
    ExcludeRules = @(
        'PSAvoidGlobalVars'                    # a profile sets globals by design
        'PSAvoidUsingWriteHost'                # prompt and aliases need console colour
        'PSUseDeclaredVarsMoreThanAssignments'  # profile state is read by the shell later
        'PSAvoidUsingInvokeExpression'         # zoxide/oh-my-posh init must be eval'd
        'PSUseApprovedVerbs'                   # user-facing names like rg-smart stay short
        'PSReviewUnusedParameter'              # helpers read $DryRun/$Force from script scope
    )
}

