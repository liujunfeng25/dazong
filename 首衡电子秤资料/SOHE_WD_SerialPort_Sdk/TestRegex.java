import java.util.regex.Pattern;
import java.util.regex.Matcher;

public class TestRegex {
    public static void main(String[] args) {
        String pattern = "^VA,([0-9]{1,3}),([0-9]{2}),([SUO]),([NG]),([\\+\\-])\\s*([0-9\\.]+),\\s*([0-9\\.]+)\\s*(kg|g|lb)\\s*\\r?\\n?$";
        String data = "VA,01,28,S,N,-   1.798,   0.000 kg";
        
        Pattern p = Pattern.compile(pattern, Pattern.CASE_INSENSITIVE);
        Matcher m = p.matcher(data);
        
        System.out.println("Pattern: " + pattern);
        System.out.println("Data: " + data);
        System.out.println("Matches: " + m.matches());
        
        if (m.matches()) {
            for (int i = 1; i <= m.groupCount(); i++) {
                System.out.println("Group " + i + ": [" + m.group(i) + "]");
            }
        }
    }
}